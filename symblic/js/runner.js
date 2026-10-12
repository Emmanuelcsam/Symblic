'use strict';
// runner.js: the node child of the JavaScript adapter (symblic/js/check.py). Started only by that module, from a
// copy in a fresh scratch directory, inside symblic/sandbox/landlock.py (Landlock, no network, no unix sockets,
// scrubbed environment).
//
// stdin:  {"pieces": [text, ...] (or "source": text), "cases": [{"call": js expression}], "timeout_ms": n}
// stdout: {"version": 4, "results": [{"ok": true, "value": json text} | {"ok": false, "kind": "syntax"|"error"|
//          "timeout"|"resource"|"result"|"redefine", "error": text, "piece": n|null, "line": n|null}]}
//
// The pieces run in order as separate classic scripts in the case's realm, like consecutive <script> blocks: their
// `const`s and functions are visible to the pieces after them. A piece that replaces a function an earlier piece
// defined fails with kind "redefine". A classic script may declare a function twice and the last one silently
// wins (2026-10-04: a unit pasted in its own copies of two earlier units' functions and broke every check after it);
// `const`/`let`/`class` already fail with "already declared".
//
// Every case runs in a FRESH V8 context made from a null-prototype object: nothing from this realm is passed in, only
// strings come back (JSON.stringify runs inside the context), and code generation from strings (eval, new Function)
// is off inside it, which closes the constructor-chain escape. Math.random throws, Date is fixed and console is a
// no-op, so a result depends only on the source and the call.
const vm = require('node:vm');
const acorn = require('./acorn.js');

const VERSION = 4;
const MAX_PARSE_TOKENS = 100000, MAX_PARSE_NODES = 100000, MAX_PARSE_DEPTH = 256;
const PRELUDE = `
  'use strict';
  // This immutable lexical binding cannot be replaced by another script's
  // global assignment or lexical declaration. Capture intrinsics before any
  // candidate executes, including mutations performed inside the tested call.
  const __symblicEncodeResult = (function () {
    const stringify = JSON.stringify, finite = Number.isFinite, text = String, Fail = Error;
    return Object.freeze(function (value) {
      const encoded = stringify(value === undefined ? null : value, function (key, item) {
        return (typeof item === 'number' && !finite(item)) ? { '#number': text(item) } : item;
      });
      if (typeof encoded !== 'string') throw new Fail('the result is not JSON');
      return encoded;
    });
  })();
  (function () {
    const fixed = 1700000000000;
    Math.random = function () { throw new Error('Math.random is not available in a deterministic check'); };
    const RealDate = Date;
    globalThis.Date = class Date extends RealDate {
      constructor(...a) { if (a.length) super(...a); else super(fixed); }
      static now() { return fixed; }
    };
    globalThis.console = { log() {}, warn() {}, error() {}, info() {}, debug() {} };
  })();
`;

function readStdin() {
  return new Promise((resolve) => {
    const chunks = [];
    process.stdin.on('data', (c) => chunks.push(c));
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
  });
}

// where an error happened: the innermost frame in one of the pieces
function placeOf(e) {
  const m = String((e && e.stack) || '').match(/piece-(\d+)\.js:(\d+)/);
  return m ? { piece: Number(m[1]), line: Number(m[2]) } :
    { piece: (e && e.piece) || null, line: (e && e.line) || null };
}

// Node versions differ when a classic script declares a frozen global function:
// some silently keep the old function. Detect declarations before execution,
// using the pinned parser in this trusted realm, never candidate intrinsics.
function parserBudget() {
  const error = new Error('the JavaScript declaration preflight exceeded its parser budget');
  error.resource = true;
  throw error;
}

function patternNames(pattern) {
  const names = [], pending = [pattern];
  while (pending.length) {
    const node = pending.pop();
    if (!node) continue;
    if (node.type === 'Identifier') names.push(node.name);
    else if (node.type === 'RestElement') pending.push(node.argument);
    else if (node.type === 'AssignmentPattern') pending.push(node.left);
    else if (node.type === 'ArrayPattern') pending.push(...node.elements);
    else if (node.type === 'ObjectPattern') {
      for (const property of node.properties) pending.push(property.type === 'RestElement' ? property.argument : property.value);
    }
  }
  return names;
}

function lexicalNames(statements) {
  const names = [];
  for (const node of statements) {
    if (node.type === 'VariableDeclaration' && node.kind !== 'var') {
      for (const declaration of node.declarations) names.push(...patternNames(declaration.id));
    } else if ((node.type === 'ClassDeclaration' || node.type === 'FunctionDeclaration') && node.id) names.push(node.id.name);
  }
  return names;
}

// Resolve writes against the complete lexical/var scopes of this piece, not
// against spelling alone. In particular body vars cannot shadow a write in a
// parameter default. No candidate code executes during this analysis.
function writeAnalysis(ast) {
  function scope(parent, kind, strict) {
    const out = {parent, kind, strict, names: new Set(), deferred: !!parent && parent.deferred};
    out.vars = !parent || kind === 'function' ? out : parent.vars;
    return out;
  }
  function children(node) {
    const out = [];
    for (const key of Object.keys(node)) {
      if (key === 'loc' || key === 'regex' || (key === 'value' && node.type === 'Literal')) continue;
      const child = node[key];
      if (Array.isArray(child)) out.push(...child.filter(x => x && typeof x.type === 'string'));
      else if (child && typeof child.type === 'string') out.push(child);
    }
    return out;
  }
  function bind(pattern, owner) { for (const name of patternNames(pattern)) owner.names.add(name); }
  const strictBody = body => body.some(n => n.directive === 'use strict');
  const root = scope(null, 'global', strictBody(ast.body));
  const refs = [], promotions = [], pending = [{node: ast, owner: root, depth: 0}];
  let nodes = 0, properties = false;
  while (pending.length) {
    const {node, owner, depth} = pending.pop();
    if (++nodes > MAX_PARSE_NODES || depth > MAX_PARSE_DEPTH) parserBudget();
    const push = (child, at = owner) => child && pending.push({node: child, owner: at, depth: depth + 1});
    const write = target => {
      for (const name of patternNames(target)) refs.push({name, owner, line: target.loc.start.line});
    };
    if (node.type === 'MemberExpression' || node.type === 'ObjectPattern' ||
        (node.type === 'Identifier' && ['__defineGetter__', '__defineSetter__'].includes(node.name))) properties = true;
    if (node.type === 'AssignmentExpression') write(node.left);
    if (node.type === 'UpdateExpression' || (node.type === 'UnaryExpression' && node.operator === 'delete')) write(node.argument);
    if (node.type === 'VariableDeclaration') {
      for (const declaration of node.declarations) {
        bind(declaration.id, node.kind === 'var' ? owner.vars : owner);
        if (node.kind === 'var' && declaration.init) write(declaration.id);
      }
    }
    if (['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression'].includes(node.type)) {
      if (node.type === 'FunctionDeclaration') {
        owner.names.add(node.id.name);
        if (owner !== owner.vars && !owner.strict && !node.async && !node.generator) {
          promotions.push({name: node.id.name, owner});
        }
      }
      const strict = owner.strict || (node.body.type === 'BlockStatement' && strictBody(node.body.body));
      const named = scope(owner, 'name', strict);
      if (node.type === 'FunctionExpression' && node.id) named.names.add(node.id.name);
      const params = scope(named, 'params', strict);
      params.deferred = true;
      if (node.type !== 'ArrowFunctionExpression') params.names.add('arguments');
      for (const param of node.params) { bind(param, params); push(param, params); }
      const body = scope(params, 'function', strict);
      // The function body is its var scope. Nested blocks get separate scopes.
      if (node.body.type === 'BlockStatement') for (const child of node.body.body) push(child, body);
      else push(node.body, body);
      continue;
    }
    if (node.type === 'BlockStatement' || node.type === 'StaticBlock') {
      const block = scope(owner, node.type === 'StaticBlock' ? 'function' : 'block', owner.strict);
      for (const child of node.body) push(child, block);
      continue;
    }
    if (node.type === 'CatchClause') {
      const caught = scope(owner, 'catch', owner.strict);
      caught.simpleCatch = node.param && node.param.type === 'Identifier';
      bind(node.param, caught); push(node.param, caught); push(node.body, caught); continue;
    }
    if (node.type === 'SwitchStatement') {
      push(node.discriminant);
      const block = scope(owner, 'block', owner.strict);
      for (const child of node.cases) push(child, block);
      continue;
    }
    if (['ForStatement', 'ForInStatement', 'ForOfStatement'].includes(node.type)) {
      const block = scope(owner, 'block', owner.strict);
      if (node.type !== 'ForStatement') {
        if (node.left.type === 'VariableDeclaration' && node.left.kind === 'var') {
          for (const declaration of node.left.declarations) {
            refs.push(...patternNames(declaration.id).map(name => ({name, owner: block, line: declaration.loc.start.line})));
          }
        } else if (node.left.type !== 'VariableDeclaration') {
          refs.push(...patternNames(node.left).map(name => ({name, owner: block, line: node.left.loc.start.line})));
        }
      }
      for (const child of children(node)) push(child, block);
      continue;
    }
    if (node.type === 'ClassDeclaration' || node.type === 'ClassExpression') {
      properties = true;
      if (node.type === 'ClassDeclaration' && node.id) owner.names.add(node.id.name);
      const cls = scope(owner, 'class', true);
      if (node.id) cls.names.add(node.id.name);
      push(node.superClass, cls); push(node.body, cls); continue;
    }
    if (node.type === 'PropertyDefinition' && !node.static) {
      const field = scope(owner, 'field', owner.strict);
      field.deferred = true;
      if (node.computed) push(node.key);
      push(node.value, field); continue;
    }
    if (node.type === 'WithStatement') {
      properties = true; push(node.object);
      push(node.body, scope(owner, 'with', owner.strict)); continue;
    }
    for (const child of children(node)) push(child);
  }
  for (const {name, owner} of promotions) {
    let outer = owner.parent, blocked = false;
    while (outer && outer !== owner.vars) {
      if (outer.names.has(name) && !(outer.kind === 'catch' && outer.simpleCatch)) { blocked = true; break; }
      outer = outer.parent;
    }
    if (!blocked) owner.vars.names.add(name);
  }
  const writes = [];
  for (const ref of refs) {
    let at = ref.owner;
    while (at && at !== root && at.kind !== 'with' && !at.names.has(ref.name)) at = at.parent;
    if (!at || at === root) writes.push({name: ref.name, line: ref.line, deferred: ref.owner.deferred});
  }
  return {writes, properties};
}

function functionDeclarations(source, piece) {
  try {
    let tokens = 0, nodes = 0;
    const ast = acorn.parse(source, {ecmaVersion: 2022, sourceType: 'script', locations: true,
      allowHashBang: true, onToken() { if (++tokens > MAX_PARSE_TOKENS) parserBudget(); }});
    const strict = ast.body.some(node => node.directive === 'use strict');
    const found = [], pending = [{node: ast, blocked: new Set(), depth: 0, top: false}];
    while (pending.length) {
      const {node, blocked, depth, top} = pending.pop();
      if (++nodes > MAX_PARSE_NODES || depth > MAX_PARSE_DEPTH) parserBudget();
      if (node.type === 'FunctionDeclaration') {
        // Annex B may also install a sloppy, ordinary block function globally.
        // Enclosing lexical bindings prevent that promotion. Strict, async and
        // generator block functions are local, as are all nested function bodies.
        if (top || (!strict && !node.async && !node.generator && !blocked.has(node.id.name))) {
          found.push({name: node.id.name, line: node.loc.start.line});
        }
        continue;
      }
      if (['FunctionExpression', 'ArrowFunctionExpression', 'ClassDeclaration', 'ClassExpression'].includes(node.type)) continue;
      let names = [], children;
      if (node.type === 'Program' || node.type === 'BlockStatement') names = lexicalNames(node.body);
      else if (node.type === 'SwitchStatement') {
        const statements = node.cases.flatMap(branch => branch.consequent);
        names = lexicalNames(statements);
        children = [node.discriminant, ...node.cases.map(branch => branch.test).filter(Boolean), ...statements];
      } else if (node.type === 'ForStatement' && node.init) names = lexicalNames([node.init]);
      else if (['ForInStatement', 'ForOfStatement'].includes(node.type)) names = lexicalNames([node.left]);
      // Annex B permits a var with the same name as a simple catch parameter;
      // destructuring catch parameters still prevent global promotion.
      else if (node.type === 'CatchClause' && node.param && node.param.type !== 'Identifier') names = patternNames(node.param);
      if (!children) {
        children = [];
        for (const key of Object.keys(node)) {
          if (key === 'loc' || key === 'regex' || (key === 'value' && node.type === 'Literal')) continue;
          const child = node[key];
          if (Array.isArray(child)) children.push(...child.filter(item => item && typeof item.type === 'string'));
          else if (child && typeof child.type === 'string') children.push(child);
        }
      }
      for (const child of children) {
        const next = new Set(blocked);
        for (const name of names) {
          // A declaration's own block binding does not block its Annex B copy;
          // a same-named binding inherited from an enclosing scope still does.
          if (!(child.type === 'FunctionDeclaration' && child.id.name === name)) next.add(name);
        }
        pending.push({node: child, blocked: next, depth: depth + 1, top: node.type === 'Program'});
      }
    }
    return {found, ...writeAnalysis(ast)};
  } catch (error) {
    error.piece = piece;
    error.line = error.loc ? error.loc.line : null;
    if (error instanceof RangeError) error.resource = true;
    // Unexpected parser failures never become evidence against the candidate.
    if (!(error instanceof SyntaxError)) error.resource = true;
    return {error};
  }
}

// The host retains descriptors of the context's global functions. Candidates
// never receive this map, and their Object/JSON/Symbol bindings cannot forge it.
// Reading descriptors does not invoke user-defined property getters.
function functionsOf(ctx) {
  const found = new Map();
  for (const name of Object.getOwnPropertyNames(ctx)) {
    const descriptor = Object.getOwnPropertyDescriptor(ctx, name);
    if (descriptor && typeof descriptor.value === 'function') found.set(name, descriptor.value);
  }
  return found;
}

function protectBindings(ctx, opts) {
  // Protect earlier global callables while later scripts and cases execute,
  // including temporary reassignments that a before/after snapshot would miss.
  // Accessors retain their original getters/setters but cannot be replaced or
  // shadowed by a new global lexical declaration.
  for (const name of Object.getOwnPropertyNames(ctx)) {
    const d = Object.getOwnPropertyDescriptor(ctx, name);
    if (d && (typeof d.value === 'function' || d.get || d.set)) {
      // A contextified global property alone does not always prevent a later
      // lexical declaration in V8. Record a real global var declaration too.
      // Only identifier tokens are inserted; reserved words are not bindings.
      if (/^[$_\p{ID_Start}][$\u200c\u200d_\p{ID_Continue}]*$/u.test(name)) {
        let declaration;
        try { declaration = new vm.Script(`var ${name};`, {filename: 'bindings.js'}); }
        catch (e) { if (!(e instanceof SyntaxError)) throw e; }
        if (declaration) declaration.runInContext(ctx, opts);
      }
      Object.defineProperty(ctx, name, { ...d, configurable: false,
        ...('value' in d ? { writable: false } : {}) });
    }
  }
}

function changedBindingError(ctx, before, piece = null) {
  if (!before) return null;
  const changed = [];
  for (const [name, original] of before) {
    const descriptor = Object.getOwnPropertyDescriptor(ctx, name);
    if (!descriptor || descriptor.value !== original) changed.push(name);
  }
  if (!changed.length) return null;
  const names = changed.slice(0, 8).map(String).join(', ');
  const error = new Error(`it defines ${names} again, but the code it runs with already defines ` +
    `${changed.length === 1 ? 'it' : 'them'}. Remove your own copies and call the existing ones.`);
  error.redefine = true; error.piece = piece;
  return error;
}

function incomplete(error) {
  return error && (error.code === 'ERR_SCRIPT_EXECUTION_TIMEOUT' || error.resource);
}

function runCase(pieces, declarations, call, timeout, protect = true) {
  const ctx = vm.createContext(Object.create(null), {
    name: 'symblic-check', codeGeneration: { strings: false, wasm: false }, microtaskMode: 'afterEvaluate',
  });
  const opts = { timeout, breakOnSigint: false };
  vm.runInContext(PRELUDE, ctx, { ...opts, filename: 'prelude.js' });
  for (let i = 0; i < pieces.length; i++) {
    const before = i > 0 ? functionsOf(ctx) : null;
    if (declarations[i].error) throw declarations[i].error;
    const repeated = before && [...declarations[i].found, ...declarations[i].writes].find(row => before.has(row.name));
    if (repeated) {
      const error = new Error(`it defines ${repeated.name} again, but the code it runs with already defines it. ` +
        'Remove your own copies and call the existing ones.');
      error.redefine = true; error.piece = i + 1; error.line = repeated.line;
      throw error;
    }
    if (i > 0 && protect) protectBindings(ctx, opts);
    try {
      vm.runInContext(pieces[i], ctx, { ...opts, filename: `piece-${i + 1}.js` });
    } catch (error) {
      // Retained mutation is still observable when later candidate code throws.
      // Incomplete execution remains a resource observation, never a verdict.
      const changed = !incomplete(error) && changedBindingError(ctx, before, i + 1);
      if (changed) throw changed;
      const name = before && [...before.keys()].find(name =>
        String(error.message) === `Cannot redefine property: ${name}` ||
        String(error.message) === `Identifier '${name}' has already been declared`);
      if (name) {
        const e = new Error(`it defines ${name} again, but the code it runs with already defines it. ` +
          'Remove your own copies and call the existing ones.');
        e.redefine = true; e.piece = i + 1; throw e;
      }
      throw error;
    }
    const changed = changedBindingError(ctx, before, i + 1);
    if (changed) throw changed;
  }
  const beforeCall = functionsOf(ctx);
  const callAst = functionDeclarations('(' + call + '\n)', null);
  if (callAst.error) throw callAst.error;
  const deferredWrites = declarations.flatMap((row, index) =>
    row.writes.filter(write => write.deferred).map(write => ({...write, piece: index + 1})));
  const callWrite = [...callAst.writes, ...deferredWrites].find(row => beforeCall.has(row.name));
  if (callWrite) {
    const e = new Error(`it defines ${callWrite.name} again, but the code it runs with already defines it. ` +
      'Remove your own copies and call the existing ones.');
    e.redefine = true; e.piece = callWrite.piece || null; e.line = callWrite.line; throw e;
  }
  if (protect) protectBindings(ctx, opts);
  let out;
  try {
    out = vm.runInContext(
      `__symblicEncodeResult((${call}\n))`,
      ctx, { ...opts, filename: 'case.js' });
  } catch (error) {
    const changed = !protect && !incomplete(error) && changedBindingError(ctx, beforeCall);
    if (changed) throw changed;
    throw error;
  }
  if (!protect) {
    const changed = changedBindingError(ctx, beforeCall);
    if (changed) throw changed;
  }
  if (typeof out !== 'string') throw new Error('the result is not JSON');
  return out;
}

(async () => {
  let req;
  try { req = JSON.parse(await readStdin()); } catch (e) {
    process.stdout.write(JSON.stringify({ version: VERSION, fatal: 'bad request: ' + e.message }));
    return;
  }
  const timeout = Math.max(50, Math.min(Number(req.timeout_ms) || 2000, 20000));
  const pieces = Array.isArray(req.pieces) ? req.pieces.map(String) : [String(req.source || '')];
  const declarations = pieces.map((source, index) => functionDeclarations(source, index + 1));
  const results = [];
  for (const c of req.cases || []) {
    try {
      const call = String(c.call || 'undefined');
      const value = runCase(pieces, declarations, call, timeout);
      // Classic-script globals have surprising frozen-write semantics. Run a
      // second independent realm with the artifact's original writable globals
      // whenever property/reflection access could bypass identifier analysis.
      // No Proxy or strict-mode rewrite changes the candidate's JavaScript.
      const callAst = functionDeclarations('(' + call + '\n)', null);
      if (declarations.some(row => row.properties) || callAst.properties) {
        const actual = runCase(pieces, declarations, call, timeout, false);
        if (actual !== value) {
          const e = new Error('the code changes behaviour when prior callable bindings have their artifact semantics. ' +
            'Do not replace dependencies through property aliases or reflection.');
          e.redefine = true; throw e;
        }
      }
      results.push({ ok: true, value });
    } catch (e) {
      const msg = (e && e.message) ? String(e.message) : String(e);
      const kind = (e && e.code === 'ERR_SCRIPT_EXECUTION_TIMEOUT') ? 'timeout' : (e && e.resource) ? 'resource' : (e && e.redefine) ? 'redefine' :
        (e && e.name === 'SyntaxError') ? 'syntax' : (msg === 'the result is not JSON' ? 'result' : 'error');
      const name = (e && e.name && !['timeout', 'result', 'redefine'].includes(kind)) ? e.name + ': ' : '';
      const where = placeOf(e);
      results.push({ ok: false, kind, error: (name + msg).slice(0, 400), piece: where.piece, line: where.line });
    }
  }
  process.stdout.write(JSON.stringify({ version: VERSION, results }));
})();
