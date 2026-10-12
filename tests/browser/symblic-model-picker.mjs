// Real page/assets, isolated browser, synthetic inventories and every API mocked.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {test, launch, open as openPage, noHorizontalScroll} from './host-harness.mjs';

async function open(...args) {
  const session = await openPage(...args);
  await session.page.locator('.sy-native-settings > summary').click();
  return session;
}

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

const local = (model, node, extra = {}) => ({id: `ollama:${model}@${node}`, engine: 'ollama', model, node,
  kind: 'local', title: `${model} · ${node}`, installed: true, typed_ask: true, selectable: true,
  ready: false, status: 'unprobed', ...extra});
const rows = [local('deepseek-r1:1.5b', 'host'), local('qwen2.5:0.5b', 'host'),
  local('gemma3:1b', 'node-b', {ready: true, status: 'cached'}),
  local('nomic-embed-text:latest', 'host', {typed_ask: false, selectable: false, status: 'embedding_only', note: 'Embedding-only model.'}),
  local('big:32b', 'node-b', {selectable: false, status: 'memory_limit', note: 'Exceeds memory limit.'})];

function fixture(calls, state) {
  return async (request, url) => {
    calls.push({method: request.method(), path: url.pathname});
    if (url.pathname === '/api/runner/engines') return state.missing ? {status: 404, json: {}} : {json: {
      engines: state.refreshed ? [...rows, local('tiny:0.1b', 'node-d')] : rows,
      model_sources: {ollama: {installed_count: 5}}, councils: [], errors: []}};
    if (url.pathname === '/api/runner/engines/refresh') {
      if (request.method() === 'POST') { state.refreshed = true; return {json: {accepted: true}}; }
      return {json: {refresh: {state: 'done', active: false, completed: 3, total: 3}}};
    }
    if (url.pathname.endsWith('/logic/compile')) return {json: {
      source: 'program Proof.\nask proof: Bool "Build the proof.".\nshow proof.', inputs: {}, options: {max_calls: 4},
      formalization: {goal: 'Goal', premises: [], certificate_format: 'steps'}, assurance: 'Fixture task.'}};
    if (url.pathname.endsWith('/check')) return {json: {ok: true, errors: [], warnings: [], inputs: [], plan: []}};
    if (url.pathname.endsWith('/meta')) return {json: {version: 'fixture', examples: [], features: {}}};
    return {json: {}};
  };
}

for (const mobile of [false, true]) test(`model inventory: all installed choices and exact Logic handoff (${mobile ? 'phone dark' : 'desktop'})`, async () => {
  const calls = [], state = {};
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixture(calls, state), {mobile});
  try {
    await page.evaluate(theme => Studio.setTheme(theme), mobile ? 'dark' : 'light');
    await page.locator('#syApps option[value="ollama:deepseek-r1:1.5b@host"]').waitFor({state: 'attached'});
    assert.equal(calls.some(c => c.path.endsWith('/engines/refresh')), false);
    assert.equal(await page.locator('#syApps option[value*="nomic-embed"]').isDisabled(), true);
    assert.equal(await page.locator('#syApps option[value*="big:32b"]').isDisabled(), true);
    await page.locator('#syApps input').fill('deepseek');
    assert.equal(await page.locator('#syApps option[value*="qwen2.5"]').count(), 0);
    await page.locator('#syApps select').selectOption('ollama:deepseek-r1:1.5b@host');
    assert.equal(await page.locator('#syBy').inputValue(), 'ollama:deepseek-r1:1.5b@host');
    assert.match(await page.locator('#syApps').textContent(), /explicitly/);
    await page.locator('#syApps input').fill('');
    await page.locator('#syApps button').click();
    await page.locator('#syApps option[value="ollama:tiny:0.1b@node-d"]').waitFor({state: 'attached'});
    assert.equal(await page.locator('#syBy').inputValue(), 'ollama:deepseek-r1:1.5b@host');
    await page.locator('#syPick').click();
    await page.locator('.sp-sheet button[aria-label="Add ollama:deepseek-r1:1.5b@host"]').waitFor();
    assert.equal(await page.locator('.sp-sheet button[aria-label*="nomic-embed"]').isDisabled(), true);
    await page.locator('.sp-sheet input[type="search"]').fill('deepseek');
    assert.equal(await page.locator('.sp-sheet .sp-row:visible').count(), 1);
    await page.keyboard.press('Escape');
    await page.evaluate(() => Studio.go('logic'));
    await page.locator('#sy-logic-applicator select').selectOption('ollama:qwen2.5:0.5b@host');
    await page.getByRole('button', {name: 'Prepare proof task', exact: true}).click();
    await page.getByRole('button', {name: 'Open in Write', exact: true}).click();
    assert.equal(await page.locator('#syBy').inputValue(), 'ollama:qwen2.5:0.5b@host');
    assert.match(await page.locator('#sySrc').inputValue(), /program Proof/);
    assert.equal(await noHorizontalScroll(page), true);
    assert.ok(await page.locator('#syApps select').evaluate(e => parseFloat(getComputedStyle(e).fontSize) >= 16));
    state.missing = true;
    await page.evaluate(() => { Studio.go('plan'); Studio.go('write'); });
    await page.locator('#syApps').getByText(/current\/manual choice is kept/).waitFor();
    assert.equal(await page.locator('#syBy').inputValue(), 'ollama:qwen2.5:0.5b@host');
    assert.equal(calls.some(c => /\/(run|launch|generate|chat)$/.test(c.path)), false);
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});
