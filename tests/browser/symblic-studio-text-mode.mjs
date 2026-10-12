// The automation studio's early Symblic text mode (web/studio/js/symblic/): parse a text program, compile it to a
// workflow graph and list its plan. Pure ES modules; runs with Node.js alone, no browser and no host.
//   node --test tests/browser/symblic-studio-text-mode.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const base = new URL('../../web/studio/js/symblic/', import.meta.url);
const {DEFAULT_SOURCE} = await import(new URL('constants.js', base));
const {parseSymblic} = await import(new URL('parser.js', base));
const {buildWorkflow} = await import(new URL('compiler.js', base));
const {buildPlanItems} = await import(new URL('plan.js', base));
const {normalizeDefaults} = await import(new URL('settings.js', base));
const defaults = normalizeDefaults({});

test('the example program parses into five steps in two blocks without warnings', () => {
  const parsed = parseSymblic(DEFAULT_SOURCE, defaults);
  assert.equal(parsed.workflowName, 'Symblic Example');
  assert.deepEqual(parsed.stats, {lines: 16, steps: 5, blocks: 2});
  assert.deepEqual(parsed.warnings, []);
});

test('the example compiles to a start node, five model steps, a branch and a loop', () => {
  const workflow = buildWorkflow(parseSymblic(DEFAULT_SOURCE, defaults), defaults);
  assert.equal(workflow.name, 'Symblic Example');
  const types = Object.values(workflow.graph.nodes).map((node) => node.type);
  assert.deepEqual(types, ['start', 'ollama', 'ollama', 'branch', 'ollama', 'ollama', 'loop', 'ollama']);
  assert.equal(workflow.graph.edges.length, 8);
});

test('the plan lists module-prefixed steps and the branch paths', () => {
  const items = buildPlanItems(parseSymblic(DEFAULT_SOURCE, defaults).statements);
  assert.equal(items[0].title, 'Intake - Summarize the client request in');
  assert.equal(items[1].meta, 'LLM - context append');
  assert.deepEqual(items.slice(2, 4).map((item) => [item.depth, item.title]), [[0, 'Intake - Branch'], [1, 'if:approved']]);
});

test('ambiguous words are reported with their line', () => {
  const parsed = parseSymblic('Program: P.\nSummarize something that might be useful.', defaults);
  assert.deepEqual(parsed.warnings, [{line: 2, message: 'Avoid ambiguous words: might.'}]);
});
