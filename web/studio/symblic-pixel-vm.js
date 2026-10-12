/* Bounded data interpreter for model-written pure functions. Never evaluates source.
 * Acorn 8.8.1 is the parser; its exact vendored bytes and MIT license accompany this file. */
(function (global) {
  'use strict';
  const INTEGRITY = typeof document === 'object' ? document.currentScript?.integrity || null : null;
  const VERSION = 1, DENIED = new Set(['__proto__', 'prototype', 'constructor', 'caller', 'callee', 'arguments']);
  const BINARY = new Set(['+', '-', '*', '/', '%', '**', '<', '<=', '>', '>=', '===', '!==', '==', '!=', '&', '|', '^', '<<', '>>', '>>>']);
  const ASSIGN = new Set(['=', '+=', '-=', '*=', '/=', '%=']);
  const LIMITS = Object.freeze({ source: 65536, nodes: 16000, astDepth: 128, steps: 2500000, cells: 600000, array: 480000, calls: 48, milliseconds: 250 });
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  function refuse(message) { throw new Error('Pixel program: ' + message); }
  function safeName(name) { return typeof name === 'string' && /^[A-Za-z_$][\w$]{0,79}$/.test(name) && !DENIED.has(name); }
  function compile(source, options = {}) {
    if (typeof source !== 'string' || source.length > LIMITS.source) refuse('source is missing or exceeds the supported limit.');
    const parser = options.parser || global.acorn;
    if (!parser || parser.version !== '8.8.1') refuse('the pinned parser is unavailable.');
    let ast;
    try { ast = parser.parse(source, { ecmaVersion: 2022, sourceType: 'script' }); }
    catch (_) { refuse('source is not supported JavaScript.'); }
    const functions = new Map(); let nodeCount = 0;
    for (const f of ast.body) {
      if (f.type === 'EmptyStatement') continue;
      if (f.type !== 'FunctionDeclaration' || !f.id || !safeName(f.id.name) || f.id.name === 'Math' || f.async || f.generator || functions.has(f.id.name))
        refuse('only distinct named, synchronous functions may appear at the top level.');
      functions.set(f.id.name, f);
    }
    if (!functions.size || functions.size > 32) refuse('the function count is outside its limit.');
    if (options.exports && (!Array.isArray(options.exports) || new Set(options.exports).size !== options.exports.length ||
        functions.size !== options.exports.length || options.exports.some(name => !functions.has(name)))) refuse('the declarations do not match the required functions.');
    const dependencies = options.dependencies;
    if (dependencies && (typeof dependencies !== 'object' || Array.isArray(dependencies) || Object.keys(dependencies).length !== functions.size ||
        [...functions.keys()].some(name => !own(dependencies, name) || !Array.isArray(dependencies[name]) || dependencies[name].some(dep => !functions.has(dep))))) refuse('invalid declared dependencies.');
    let localNames = new Set(), currentFunction = '';
    const binding = node => {
      if (node?.type !== 'Identifier' || !safeName(node.name) || node.name === 'Math' || functions.has(node.name)) refuse('unsupported local binding.');
    };
    function visit(node, depth = 0) {
      if (!node || ++nodeCount > LIMITS.nodes || depth > LIMITS.astDepth) refuse('syntax exceeds its structural budget.');
      const sub = child => visit(child, depth + 1);
      switch (node.type) {
        case 'BlockStatement': node.body.forEach(sub); break;
        case 'EmptyStatement': break;
        case 'ReturnStatement': if (!node.argument) refuse('returns must carry a value.'); sub(node.argument); break;
        case 'VariableDeclaration':
          if (!['let', 'const'].includes(node.kind) || node.declarations.length > 64) refuse('only bounded let/const declarations are supported.');
          for (const d of node.declarations) { binding(d.id); if (!d.init) refuse('local variables need an explicit initial value.'); sub(d.init); }
          break;
        case 'ExpressionStatement': sub(node.expression); break;
        case 'IfStatement': sub(node.test); sub(node.consequent); if (node.alternate) sub(node.alternate); break;
        case 'ForStatement': if (node.init) sub(node.init); if (!node.test) refuse('for loops need an explicit condition.'); sub(node.test); if (node.update) sub(node.update); sub(node.body); break;
        case 'ForOfStatement':
          if (node.await || node.left.type !== 'VariableDeclaration' || node.left.declarations.length !== 1 || node.left.declarations[0].init) refuse('for-of needs one new local binding.');
          if (!['let', 'const'].includes(node.left.kind)) refuse('for-of needs let or const.'); binding(node.left.declarations[0].id); sub(node.right); sub(node.body); break;
        case 'Identifier': if (!safeName(node.name) || !localNames.has(node.name)) refuse('unknown or forbidden local name.'); break;
        case 'Literal': if (!(node.value === null || typeof node.value === 'boolean' || (typeof node.value === 'number' && Number.isFinite(node.value)))) refuse('only finite number, Boolean and null literals are supported.'); break;
        case 'ArrayExpression': if (node.elements.length > 10000 || node.elements.some(value => !value)) refuse('sparse or oversized literal array.'); node.elements.forEach(sub); break;
        case 'ObjectExpression':
          if (node.properties.length > 64) refuse('object exceeds its field limit.');
          { const seen = new Set(); for (const p of node.properties) {
            const key = p.key?.name;
            if (p.type !== 'Property' || p.computed || p.kind !== 'init' || p.method || !safeName(key) || seen.has(key)) refuse('object properties must be distinct plain names.');
            seen.add(key); sub(p.value);
          } } break;
        case 'UnaryExpression': if (!['+', '-', '!'].includes(node.operator)) refuse('unsupported unary operation.'); sub(node.argument); break;
        case 'BinaryExpression': if (!BINARY.has(node.operator)) refuse('unsupported arithmetic or comparison.'); sub(node.left); sub(node.right); break;
        case 'LogicalExpression': if (!['&&', '||', '??'].includes(node.operator)) refuse('unsupported logical operation.'); sub(node.left); sub(node.right); break;
        case 'ConditionalExpression': sub(node.test); sub(node.consequent); sub(node.alternate); break;
        case 'MemberExpression':
          if (node.optional) refuse('optional property access is unsupported.'); sub(node.object);
          if (node.computed) sub(node.property); else if (!safeName(node.property.name)) refuse('reserved property.');
          break;
        case 'AssignmentExpression':
          if (!ASSIGN.has(node.operator) || !['Identifier', 'MemberExpression'].includes(node.left.type)) refuse('unsupported assignment.');
          sub(node.left); sub(node.right); break;
        case 'UpdateExpression': if (!['++', '--'].includes(node.operator) || !['Identifier', 'MemberExpression'].includes(node.argument.type)) refuse('unsupported update.'); sub(node.argument); break;
        case 'CallExpression':
          if (node.optional || node.arguments.length > 16 || node.arguments.some(a => a.type === 'SpreadElement')) refuse('unsupported function arguments.');
          if (node.callee.type === 'Identifier') {
            if (!functions.has(node.callee.name)) refuse('calls may name only declared functions.');
            if (dependencies && !dependencies[currentFunction].includes(node.callee.name)) refuse('call is not a declared dependency.');
          }
          else if (node.callee.type === 'MemberExpression' && !node.callee.computed && !node.callee.optional) {
            const name = node.callee.property.name;
            if (node.callee.object.type === 'Identifier' && node.callee.object.name === 'Math') {
              if (!['min', 'max', 'abs', 'floor'].includes(name)) refuse('unsupported Math operation.');
            } else { if (!['push', 'fill'].includes(name)) refuse('unsupported array method.'); sub(node.callee.object); }
          } else refuse('dynamic calls are forbidden.');
          node.arguments.forEach(sub); break;
        default: refuse('unsupported syntax: ' + node.type + '.');
      }
    }
    for (const f of functions.values()) {
      currentFunction = f.id.name; localNames = new Set(f.params.map(p => p.name));
      const pending = [f.body]; let scanned = 0;
      while (pending.length) {
        const item = pending.pop();
        if (++scanned > LIMITS.nodes) refuse('syntax exceeds its structural budget.');
        if (item.type === 'VariableDeclarator' && item.id.type === 'Identifier') localNames.add(item.id.name);
        for (const value of Object.values(item)) {
          if (value && typeof value === 'object' && typeof value.type === 'string') pending.push(value);
          else if (Array.isArray(value)) for (const child of value) if (child && typeof child.type === 'string') pending.push(child);
        }
      }
      const seen = new Set();
      for (const p of f.params) { binding(p); if (seen.has(p.name)) refuse('duplicate parameter.'); seen.add(p.name); }
      visit(f.body);
    }
    const containers = new WeakSet(), buffers = new WeakSet();
    function buffer(length) {
      if (!Number.isSafeInteger(length) || length < 1 || length > LIMITS.array) refuse('buffer size is outside its limit.');
      const value = new Uint8Array(length); containers.add(value); buffers.add(value); return value;
    }
    function primitive(value) { return value === null || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value)); }
    function call(name, args) {
      if (!functions.has(name) || !Array.isArray(args) || args.length > 16 || args.some(value => !primitive(value) && !buffers.has(value))) refuse('invalid invocation.');
      let steps = 0, cells = 0, depth = 0;
      const clock = () => global.performance ? global.performance.now() : Date.now(), started = clock();
      function tick(amount = 1) {
        steps += amount;
        if (steps > LIMITS.steps || ((steps & 1023) === 0 && clock() - started > LIMITS.milliseconds)) refuse('execution budget exhausted.');
      }
      function allocation(amount) { if ((cells += amount) > LIMITS.cells) refuse('allocation budget exhausted.'); }
      function scalar(value) { if (!primitive(value)) refuse('operation requires a finite scalar.'); return value; }
      function numeric(value) { if (typeof value !== 'number' || !Number.isFinite(value)) refuse('operation requires a finite number.'); return value; }
      function result(value) { if (typeof value === 'number' && !Number.isFinite(value)) refuse('nonfinite arithmetic result.'); return value; }
      const environment = parent => ({ parent, values: new Map() });
      function resolve(env, key) { for (let e = env; e; e = e.parent) if (e.values.has(key)) { const slot = e.values.get(key); if (!slot.initialized) refuse('local binding is not initialized: ' + key + '.'); return slot; } refuse('unknown local name: ' + key + '.'); }
      function reserve(env, declaration) { for (const d of declaration.declarations) { if (env.values.has(d.id.name)) refuse('duplicate local binding.'); env.values.set(d.id.name, { initialized: false, constant: declaration.kind === 'const' }); } }
      function declare(env, key, value, constant) { if (env.values.get(key)?.initialized) refuse('duplicate local binding.'); env.values.set(key, { value, constant, initialized: true }); }
      function location(node, env) {
        if (node.type === 'Identifier') { const slot = resolve(env, node.name); return { get: () => slot.value, set: value => { if (slot.constant) refuse('cannot assign a constant.'); slot.value = value; } }; }
        const value = expr(node.object, env);
        if (!value || !containers.has(value)) refuse('only interpreter-owned data has properties.');
        const key = node.computed ? expr(node.property, env) : node.property.name;
        const array = Array.isArray(value) || buffers.has(value);
        if (array) {
          if (key === 'length') return { get: () => value.length, set: () => refuse('array length is read-only.') };
          if (!Number.isSafeInteger(key) || key < 0 || key >= value.length) refuse('array index is outside its populated bounds.');
          return { get: () => value[key], set: item => { if (buffers.has(value) && item !== 0 && item !== 1) refuse('binary buffer accepts only zero or one.'); value[key] = item; } };
        }
        if (typeof key !== 'string' || !safeName(key) || !own(value, key)) refuse('only existing own data properties are accessible.');
        return { get: () => value[key], set: item => { value[key] = item; } };
      }
      function binary(op, a, b) {
        if (['===', '!==', '==', '!='].includes(op)) {
          scalar(a); scalar(b);
          return op === '===' ? a === b : op === '!==' ? a !== b : op === '==' ? a == b : a != b;
        }
        numeric(a); numeric(b);
        switch (op) {
          case '+': return result(a + b); case '-': return result(a - b); case '*': return result(a * b);
          case '/': return result(a / b); case '%': return result(a % b); case '**': return result(a ** b);
          case '<': return a < b; case '<=': return a <= b; case '>': return a > b; case '>=': return a >= b;
          case '&': return a & b; case '|': return a | b; case '^': return a ^ b; case '<<': return a << b; case '>>': return a >> b; case '>>>': return a >>> b;
          default: refuse('unsupported binary instruction.');
        }
      }
      function expr(node, env) {
        tick();
        switch (node.type) {
          case 'Literal': return node.value;
          case 'Identifier': return resolve(env, node.name).value;
          case 'ArrayExpression': { allocation(node.elements.length + 1); const value = node.elements.map(n => expr(n, env)); containers.add(value); return value; }
          case 'ObjectExpression': { allocation(node.properties.length + 1); const value = Object.create(null); for (const p of node.properties) value[p.key.name] = expr(p.value, env); containers.add(value); return value; }
          case 'MemberExpression': return location(node, env).get();
          case 'UnaryExpression': { const value = expr(node.argument, env); return node.operator === '!' ? !scalar(value) : node.operator === '-' ? -numeric(value) : numeric(value); }
          case 'BinaryExpression': return binary(node.operator, expr(node.left, env), expr(node.right, env));
          case 'LogicalExpression': { const value = scalar(expr(node.left, env)); return node.operator === '&&' ? value && expr(node.right, env) : node.operator === '||' ? value || expr(node.right, env) : value ?? expr(node.right, env); }
          case 'ConditionalExpression': return scalar(expr(node.test, env)) ? expr(node.consequent, env) : expr(node.alternate, env);
          case 'AssignmentExpression': { const target = location(node.left, env); const value = node.operator === '=' ? expr(node.right, env) : binary(node.operator.slice(0, -1), target.get(), expr(node.right, env)); target.set(value); return value; }
          case 'UpdateExpression': { const target = location(node.argument, env), old = numeric(target.get()), value = result(old + (node.operator === '++' ? 1 : -1)); target.set(value); return node.prefix ? value : old; }
          case 'CallExpression': {
            if (node.callee.type === 'Identifier') return invoke(node.callee.name, node.arguments.map(n => expr(n, env)));
            const member = node.callee, method = member.property.name;
            if (member.object.type === 'Identifier' && member.object.name === 'Math') {
              const values = node.arguments.map(n => numeric(expr(n, env)));
              if ((['abs', 'floor'].includes(method) && values.length !== 1) || !values.length) refuse('wrong Math argument count.');
              return result(method === 'min' ? Math.min(...values) : method === 'max' ? Math.max(...values) : method === 'abs' ? Math.abs(values[0]) : Math.floor(values[0]));
            }
            const value = expr(member.object, env), values = node.arguments.map(n => expr(n, env));
            if (!containers.has(value) || (!Array.isArray(value) && !buffers.has(value))) refuse('array method needs interpreter-owned data.');
            if (method === 'push') {
              if (!Array.isArray(value) || value.length + values.length > LIMITS.array) refuse('array growth exceeds its limit.');
              allocation(values.length); return value.push(...values);
            }
            if (values.length !== 1 || (buffers.has(value) && values[0] !== 0 && values[0] !== 1)) refuse('fill requires one valid value.');
            tick(value.length); value.fill(values[0]); return value;
          }
          default: refuse('invalid expression.');
        }
      }
      function statement(node, env) {
        tick();
        switch (node.type) {
          case 'BlockStatement': { const local = environment(env); for (const n of node.body) if (n.type === 'VariableDeclaration') reserve(local, n); for (const n of node.body) { const returned = statement(n, local); if (returned) return returned; } break; }
          case 'EmptyStatement': break;
          case 'ReturnStatement': return { value: node.argument ? expr(node.argument, env) : null };
          case 'VariableDeclaration': for (const d of node.declarations) declare(env, d.id.name, d.init ? expr(d.init, env) : null, node.kind === 'const'); break;
          case 'ExpressionStatement': expr(node.expression, env); break;
          case 'IfStatement': if (scalar(expr(node.test, env))) return statement(node.consequent, env); else if (node.alternate) return statement(node.alternate, env); break;
          case 'ForStatement': {
            const local = environment(env);
            if (node.init?.type === 'VariableDeclaration') reserve(local, node.init);
            if (node.init) node.init.type === 'VariableDeclaration' ? statement(node.init, local) : expr(node.init, local);
            while (scalar(expr(node.test, local))) { const returned = statement(node.body, local); if (returned) return returned; if (node.update) expr(node.update, local); }
            break;
          }
          case 'ForOfStatement': {
            const loop = environment(env); reserve(loop, node.left);
            const values = expr(node.right, loop);
            if (!containers.has(values) || (!Array.isArray(values) && !buffers.has(values))) refuse('for-of requires interpreter-owned array data.');
            for (let index = 0; index < values.length; index++) {
              tick(); const local = environment(env); declare(local, node.left.declarations[0].id.name, values[index], node.left.kind === 'const');
              const returned = statement(node.body, local); if (returned) return returned;
            } break;
          }
          default: refuse('invalid statement.');
        }
        return null;
      }
      function invoke(key, values) {
        tick(); const f = functions.get(key);
        if (!f || values.length !== f.params.length || ++depth > LIMITS.calls) refuse('call arity or depth limit exceeded.');
        const env = environment(null);
        f.params.forEach((p, i) => declare(env, p.name, values[i], false));
        const answer = statement(f.body, env); depth--;
        if (!answer) refuse('every invoked path must return an explicit value.');
        return answer.value;
      }
      const answer = invoke(name, args);
      if (clock() - started > LIMITS.milliseconds) refuse('execution time budget exhausted.');
      return answer;
    }
    return Object.freeze({ call, buffer, names: Object.freeze([...functions.keys()]), version: VERSION });
  }
  global.SymblicPixelVM = Object.freeze({ compile, version: VERSION, limits: LIMITS, integrity: INTEGRITY });
})(typeof window === 'object' ? window : globalThis);
