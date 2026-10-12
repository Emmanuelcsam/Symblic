'use strict';
// Trusted host harness. Candidate modules are a closed in-memory graph; no loader,
// host callback, host exception or filesystem object is installed in the realm.
const vm = require('node:vm');
const types = require('node:util').types;
const fs = require('node:fs');
const acorn = require('./acorn.js');
const PRELUDE = fs.readFileSync('./prelude.js', 'utf8');
const MAX_BYTES = 2400000, MAX_NODES = 100000, MAX_DEPTH = 256;
const INSTALL = `
const __symblicInstallModuleCheck = (() => {
  const define = Object.defineProperty, target = globalThis;
  return fn => define(target, '__symblicModuleCheck', {value: fn, writable: false, configurable: false});
})();`;
function invalid(message) { const e = new Error(message); e.policy = true; throw e; }
function budget(message) { const e = new Error(message); e.budget = true; throw e; }
function parse(source, module = true) {
  let tokens = 0, nodes = 0;
  const ast = acorn.parse(source, {ecmaVersion: 2022, sourceType: module ? 'module' : 'script',
    onToken() { if (++tokens > MAX_NODES) budget('parser token budget'); }});
  const pending = [[ast, 0]];
  while (pending.length) {
    const [node, depth] = pending.pop();
    if (++nodes > MAX_NODES || depth > MAX_DEPTH) budget('parser traversal budget');
    if (node.type === 'ImportExpression' || node.type === 'MetaProperty') invalid('dynamic import and meta properties are unsupported');
    for (const key of Object.keys(node)) {
      if (key === 'regex' || (key === 'value' && node.type === 'Literal')) continue;
      const value = node[key];
      if (Array.isArray(value)) {
        for (const child of value) {
          if (child && typeof child.type === 'string') pending.push([child, depth + 1]);
        }
      } else if (value && typeof value.type === 'string') {
        pending.push([value, depth + 1]);
      }
    }
  }
  return ast;
}
function inspect(file) {
  const ast = parse(file.text);
  const imports = [], exports = [], names = [];
  for (const node of ast.body) {
    if (node.type === 'ImportDeclaration') {
      if (node.specifiers.some(s => s.type !== 'ImportSpecifier' || s.local.name !== s.imported.name)) invalid('only exact named imports are supported');
      imports.push({specifier: node.source.value, names: node.specifiers.map(s => s.local.name)});
    } else if (node.type === 'ExportNamedDeclaration' && !node.declaration) {
      if (node.specifiers.some(s => s.local.name !== s.exported.name)) invalid('only exact named exports are supported');
      const selected = node.specifiers.map(s => s.exported.name);
      exports.push(...selected);
      if (node.source) imports.push({specifier: node.source.value, names: selected});
    } else if (node.type === 'FunctionDeclaration' && file.role === 'unit') names.push(node.id.name);
    else if (node.type === 'EmptyStatement' || (node.type === 'ExpressionStatement' && node.directive === 'use strict')) continue;
    else invalid('only passive function declarations and generated imports/exports are supported');
  }
  if (JSON.stringify(imports) !== JSON.stringify(file.imports.map(x => ({specifier:x.specifier,names:x.names}))) ||
      JSON.stringify(exports) !== JSON.stringify(file.exports) ||
      (file.role === 'unit' && JSON.stringify([...names].sort()) !== JSON.stringify([...file.exports].sort())) ||
      names.some(x => x.startsWith('__symblic'))) invalid('module surface differs from compiler manifest');
}
function outcome(error) {
  // Never invoke a candidate's message/stack/getter/toString in the host realm.
  // Native-error branding rejects proxies. Descriptor lookup does not run getters.
  if (types.isNativeError(error)) {
    const code = Object.getOwnPropertyDescriptor(error, 'code');
    if (code && code.value === 'ERR_SCRIPT_EXECUTION_TIMEOUT') return {ok:false,kind:'timeout',error:'module case exceeded its wall budget'};
  }
  return {ok:false,kind:'error',error:'module loading or case execution failed'};
}
async function runCase(files, item, timeout) {
  const context = vm.createContext(Object.create(null), {codeGeneration:{strings:false,wasm:false},microtaskMode:'afterEvaluate'});
  const end = performance.now() + timeout;
  const left = () => Math.max(1, Math.ceil(end - performance.now()));
  try {
    new vm.Script(PRELUDE + INSTALL).runInContext(context, {timeout:left()});
    const modules = new Map();
    for (const file of files) modules.set(file.path, new vm.SourceTextModule(file.text,{context,identifier:file.path}));
    const checkImports = item.imports.map(x => `import {${x.names.join(',')}} from ${JSON.stringify(x.specifier)};`).join('\n');
    const test = new vm.SourceTextModule(checkImports + '\n__symblicInstallModuleCheck(() => {try {return \"v\" + __symblicEncodeResult((' + item.call + '\n));} catch (_) {return \"e\";}});',
      {context,identifier:'__symblic_test__.mjs'});
    const links = new Map(files.map(file => [file.path, new Map(file.imports.map(x => [x.specifier,x.path]))]));
    links.set('__symblic_test__.mjs', new Map(item.imports.map(x => [x.specifier,x.path])));
    await test.link((specifier, referencing) => {
      const target = links.get(referencing.identifier)?.get(specifier);
      if (!target || !modules.has(target)) invalid('unregistered static import');
      return modules.get(target);
    });
    // No candidate function is invoked while native module promises settle.
    // A bounded empty evaluation drains the context queue used by Node 22.
    const loading = test.evaluate({timeout:left()});
    const drain = new Promise((resolve, reject) => setImmediate(() => {
      try { new vm.Script('').runInContext(context,{timeout:left()}); resolve(); } catch (e) { reject(e); }
    }));
    await Promise.all([loading, drain]);
    const value = new vm.Script('__symblicModuleCheck()', {displayErrors:false}).runInContext(context,{timeout:left(),displayErrors:false});
    if (typeof value !== 'string') return {ok:false,kind:'result',error:'module case did not return encoded JSON text'};
    if (value === 'e') return {ok:false,kind:'error',error:'module case threw inside its realm'};
    if (!value.startsWith('v')) return {ok:false,kind:'result',error:'module result protocol differs'};
    return {ok:true,value:value.slice(1)};
  } catch (error) { return outcome(error); }
}
async function main(request) {
  if (typeof vm.SourceTextModule !== 'function') return {version:1,status:'unsupported',reason:'SourceTextModule is unavailable',results:[]};
  if (!request || !Array.isArray(request.files) || request.files.length < 2 || request.files.length > 129 ||
      !Array.isArray(request.cases) || request.cases.length < 1 || request.cases.length > 200 ||
      !Number.isInteger(request.timeout_ms) || request.timeout_ms < 1 || request.timeout_ms > 3000) invalid('request bounds');
  let bytes = 0;
  for (const file of request.files) { bytes += Buffer.byteLength(file.text); inspect(file); }
  if (bytes > 400000) invalid('aggregate module byte budget');
  for (const item of request.cases) {
    const ast = parse('(' + item.call + '\n)', false);
    if (ast.body.length !== 1 || ast.body[0].type !== 'ExpressionStatement') invalid('checks must be one expression');
  }
  const results = [];
  for (const item of request.cases) results.push(await runCase(request.files,item,request.timeout_ms));
  return {version:1,status:'completed',results};
}
let bytes = 0, chunks = [], oversized = false;
process.stdin.on('data', chunk => { bytes += chunk.length; if (bytes > MAX_BYTES) {oversized=true;chunks=[];} else if (!oversized) chunks.push(chunk); });
process.stdin.on('end', async () => {
  let result;
  try { if (oversized) invalid('input byte budget'); result = await main(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
  catch (error) { const limited = error.budget || error instanceof RangeError; result = {version:1,status:limited ? 'inconclusive' : 'invalid',reason:limited ? 'module parser resource bound exceeded' : 'module syntax, surface or input policy rejected',results:[]}; }
  process.stdout.write(JSON.stringify(result));
});
