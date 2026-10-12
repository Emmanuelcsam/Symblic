// symblic-picker journeys with a fake cache-only engine catalogue: choose, preview, apply to the run, to an ask,
// as a group; explicit machine check; desktop light and phone dark. No server, model, store or machine probe.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {writeFileSync} from 'node:fs';
import {test, launch, open as openPage, axe, noHorizontalScroll} from './host-harness.mjs';

async function open(...args) {
  const session = await openPage(...args);
  await session.page.locator('.sy-native-settings > summary').click();
  return session;
}

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

const ROWS = [
  {id: 'ollama:qwen3:4b-instruct@node-a', spec: 'ollama:qwen3:4b-instruct@node-a', engine: 'ollama', model: 'qwen3:4b-instruct', node: 'node-a',
   title: 'qwen3:4b-instruct · node-a', kind: 'local', cloud: false, status: 'available', ready: true, efforts: [], typed_ask: true},
  {id: 'ollama:deepseek-r1:7b@node-d', spec: 'ollama:deepseek-r1:7b@node-d', engine: 'ollama', model: 'deepseek-r1:7b', node: 'node-d',
   title: 'deepseek-r1:7b · node-d', kind: 'local', cloud: false, status: 'available', ready: true, efforts: [], typed_ask: true},
  {id: 'claude:haiku', spec: 'claude:haiku', engine: 'claude', model: 'haiku', node: '', title: 'Claude Haiku', kind: 'cli', cloud: true,
   status: 'unprobed', ready: false, efforts: ['', 'low', 'medium', 'high'], typed_ask: true, display_only: true, note: 'No cached node placement.'},
  {id: 'gemini:flash', spec: 'gemini:flash', engine: 'gemini', model: 'flash', node: '', title: 'Gemini Flash', kind: 'web', cloud: true,
   status: 'cached', ready: true, efforts: [], typed_ask: true},
];

function fixture(calls) {
  let checked = false;
  return async (request, url) => {
    calls.push(request.method() + ' ' + url.pathname);
    if (url.pathname === '/api/runner/engines') return {json: {engines: ROWS, councils: [{id: 'council:panel'}], registry: [], methods: []}};
    if (url.pathname === '/api/runner/engines/refresh') {
      if (request.method() === 'POST') { checked = true; return {json: {accepted: true, refresh: {state: 'running', active: true}}}; }
      return {json: {refresh: {state: checked ? 'done' : 'idle', active: false, completed: 2, total: 2}}};
    }
    const route = url.pathname.replace('/api/automation/symblic/', '');
    if (route === 'meta') return {json: {version: 'fixture', examples: []}};
    if (route === 'check' || route === 'paper/check') return {json: {ok: true, plan: [], errors: [], warnings: [], inputs: []}};
    if (route === 'runs') return {json: {runs: []}};
    return undefined;
  };
}

const texts = [];
for (const mobile of [false, true]) {
  test(`picker: choose, preview, apply (${mobile ? 'phone dark' : 'desktop light'})`, async () => {
    const calls = [];
    const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixture(calls), {mobile});
    try {
      await page.evaluate(theme => Studio.setTheme(theme), mobile ? 'dark' : 'light');
      await page.locator('#syPick').click();
      const sheet = page.locator('.sp-sheet');
      await sheet.locator('.sp-row').first().waitFor();
      assert.equal(calls.filter(c => c.includes('engines/refresh')).length, 0, 'opening never checks the machines');
      assert.ok(await sheet.locator('summary', {hasText: 'Local models · DeepSeek'}).count() === 1);

      // one agent -> the run default through the page's own change handler
      await sheet.locator('button[aria-label="Add ollama:deepseek-r1:7b@node-d"]').click();
      assert.equal(await sheet.locator('.sp-text').textContent(), 'by "ollama:deepseek-r1:7b@node-d"');
      texts.push(await sheet.locator('.sp-text').textContent());
      assert.equal(await noHorizontalScroll(page), true);
      assert.deepEqual(await axe(page), []);
      await sheet.locator('button', {hasText: 'Use for the whole run'}).click();
      assert.equal(await page.locator('#syBy').inputValue(), 'ollama:deepseek-r1:7b@node-d');
      assert.equal(await page.locator('.sp-sheet').count(), 0);

      // a crew with effort and weight, applied to the ask at the cursor
      await page.locator('#sySrc').fill('ask x: Int in 0..9 "Pick a number."\nensure x = 3 else retry.\n');
      await page.locator('#sySrc').evaluate(el => el.setSelectionRange(3, 3));
      await page.locator('#syPick').click();
      await sheet.locator('.sp-row').first().waitFor();
      await sheet.locator('button[aria-label="Add ollama:qwen3:4b-instruct@node-a"]').click();
      await sheet.locator('button[aria-label="Add claude:haiku"]').click();
      await sheet.locator('select[aria-label="Effort for claude:haiku"]').selectOption('high');
      await sheet.locator('input[aria-label="Vote weight for claude:haiku"]').fill('2');
      await sheet.locator('input[aria-label="Vote weight for claude:haiku"]').dispatchEvent('change');
      await sheet.locator('input[value="escalate"]').check();
      const text = await sheet.locator('.sp-text').textContent();
      assert.equal(text, 'by ["ollama:qwen3:4b-instruct@node-a", "claude:haiku+high*2"] with route=escalate');
      texts.push(text);
      assert.ok(await sheet.locator('.sp-warn', {hasText: 'cloud opt-in'}).count() === 1);
      await sheet.locator('button', {hasText: 'Apply to the ask at the cursor'}).click();
      const src = await page.locator('#sySrc').inputValue();
      assert.equal(src.split('\n')[0], 'ask x: Int in 0..9 "Pick a number." ' + text);

      // an ask that already has `with` is never rewritten; a group is inserted instead
      await page.locator('#sySrc').fill('ask y: Int in 0..9 "Pick." with effort=low\nensure y = 1 else retry.\n');
      await page.locator('#sySrc').evaluate(el => el.setSelectionRange(2, 2));
      await page.locator('#syPick').click();
      await sheet.locator('.sp-row').first().waitFor();
      await sheet.locator('button[aria-label="Add ollama:qwen3:4b-instruct@node-a"]').click();
      await sheet.locator('button[aria-label="Add gemini:flash"]').click();
      await sheet.locator('input[value="search"]').check();
      assert.equal(await sheet.locator('button', {hasText: 'Apply to the ask at the cursor'}).isDisabled(), true);
      texts.push(await sheet.locator('.sp-text').textContent());
      await sheet.locator('button', {hasText: 'Insert as a group'}).click();
      assert.match(await page.locator('#sySrc').inputValue(), /^group crew = \["ollama:qwen3:4b-instruct@node-a", "gemini:flash"\]\.\n/);

      // the machines are checked only on the explicit click
      await sheet.locator('button', {hasText: 'Check the machines'}).click();
      await page.waitForFunction(() => /Machines checked/.test(document.querySelector('.sp-note')?.textContent || '') ||
        /Machines checked/.test(document.querySelector('#toast')?.textContent || ''), null, {timeout: 15000});
      assert.equal(calls.filter(c => c === 'POST /api/runner/engines/refresh').length, 1);
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  });
}
test('picker v2: safe group placement, multi-line asks, no run from behind, mount API', async () => {
  const calls = [];
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixture(calls), {});
  try {
    // a group is inserted after the header, never splitting an ask from its continuation line
    const src = 'use profile=verified.\nask y: Int in 0..9 "Pick."\n  with effort=low\nensure y = 1 else retry.\n';
    await page.locator('#sySrc').fill(src);
    const at = src.indexOf('  with effort=low') + 4;
    await page.locator('#sySrc').evaluate((el, i) => el.setSelectionRange(i, i), at);
    await page.locator('#syPick').click();
    const sheet = page.locator('.sp-sheet');
    await sheet.locator('.sp-row').first().waitFor();
    await sheet.locator('button[aria-label="Add ollama:qwen3:4b-instruct@node-a"]').click();
    await sheet.locator('button[aria-label="Add gemini:flash"]').click();
    await sheet.locator('input[value="vote"]').check();
    await sheet.locator('button', {hasText: 'Insert as a group'}).click();
    const lines = (await page.locator('#sySrc').inputValue()).split('\n');
    assert.equal(lines[0], 'use profile=verified.');
    assert.match(lines[1], /^group crew = \[/);
    assert.equal(lines[2], 'ask y: Int in 0..9 "Pick."');
    assert.equal(lines[3], '  with effort=low');
    await page.keyboard.press('Escape');

    // an ask whose instruction string spans lines is never rewritten
    await page.locator('#sySrc').fill('ask z: Int in 0..9 "Pick\na number."\nensure z = 1 else retry.\n');
    await page.locator('#sySrc').evaluate(el => el.setSelectionRange(2, 2));
    await page.locator('#syPick').click();
    await sheet.locator('.sp-row').first().waitFor();
    await sheet.locator('button[aria-label="Add ollama:qwen3:4b-instruct@node-a"]').click();
    assert.equal(await sheet.locator('button', {hasText: 'Apply to the ask at the cursor'}).isDisabled(), true);

    // Ctrl+Enter with the picker open never starts a run
    await page.locator('#sySrc').focus();
    await page.keyboard.press('Control+Enter');
    assert.equal(calls.some(c => c.endsWith('/run')), false, 'no run from behind the picker');
    await page.keyboard.press('Escape');

    // another tab can mount the picker and receive the text without any editor change
    const before = await page.locator('#sySrc').inputValue();
    await page.evaluate(() => { window.__picked = null; SymblicPicker.open({onApply: (text) => { window.__picked = text; }}); });
    await sheet.locator('.sp-row').first().waitFor();
    await sheet.locator('button[aria-label="Add ollama:deepseek-r1:7b@node-d"]').click();
    await sheet.locator('button', {hasText: 'Use this'}).click();
    assert.equal(await page.evaluate(() => window.__picked), 'by "ollama:deepseek-r1:7b@node-d"');
    assert.equal(await page.locator('#sySrc').inputValue(), before);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

// v3 (root critic on picker v1): stale async work, refresh after close, unsafe asks, whole-run semantics
function fixtureV3(calls, {delayFirst = false, stuck = false} = {}) {
  let engines = 0;
  return async (request, url) => {
    calls.push(request.method() + ' ' + url.pathname);
    if (url.pathname === '/api/runner/engines') {
      engines++;
      if (delayFirst && engines === 1) { await new Promise(r => setTimeout(r, 800)); return {status: 500, json: {}}; }
      return {json: {engines: ROWS, councils: [], registry: [], methods: []}};
    }
    if (url.pathname === '/api/runner/engines/refresh') {
      if (request.method() === 'POST') return {json: {accepted: true, refresh: {state: 'running', active: true}}};
      return {json: {refresh: {state: 'running', active: stuck, completed: 0, total: 2}}};
    }
    const route = url.pathname.replace('/api/automation/symblic/', '');
    if (route === 'meta') return {json: {version: 'fixture', examples: []}};
    if (route === 'check') return {json: {ok: true, plan: [], errors: [], warnings: [], inputs: []}};
    if (route === 'runs') return {json: {runs: []}};
    return undefined;
  };
}

test('picker v3: a delayed rejected load never touches a closed or reopened sheet', async () => {
  const calls = [];
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixtureV3(calls, {delayFirst: true}), {});
  try {
    await page.locator('#syPick').click();
    await page.keyboard.press('Escape');                     // closed while the first load is still pending
    await page.locator('#syPick').click();                   // reopened: its own load succeeds
    await page.locator('.sp-sheet .sp-row').first().waitFor();
    await page.waitForTimeout(1200);                         // the first load fails after 800 ms
    assert.equal(await page.locator('.sp-sheet').count(), 1);
    assert.equal(await page.locator('.sp-sheet .sp-warn', {hasText: 'did not answer'}).count(), 0, 'no stale error in the new sheet');
    assert.ok(await page.locator('.sp-sheet .sp-row').count() >= 4);
    await page.keyboard.press('Escape');
    await page.locator('#syPick').click();
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.sp-sheet').count(), 0);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

test('picker v3: closing stops the machine-check polling', async () => {
  const calls = [];
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixtureV3(calls, {stuck: true}), {});
  try {
    await page.locator('#syPick').click();
    await page.locator('.sp-sheet .sp-row').first().waitFor();
    await page.locator('.sp-sheet button', {hasText: 'Check the machines'}).click();
    await page.waitForTimeout(2500);                         // one poll after ~2 s
    const polls = () => calls.filter(c => c === 'GET /api/runner/engines/refresh').length;
    assert.ok(polls() >= 1);
    await page.keyboard.press('Escape');
    const atClose = polls();
    await page.waitForTimeout(4500);
    assert.ok(polls() - atClose <= 1, `polling continued after close: ${polls() - atClose} more`);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

test('picker v3: comment, multi-line string and continuation asks are never rewritten; whole-run keeps options', async () => {
  const calls = [];
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixtureV3(calls), {});
  try {
    const sheet = page.locator('.sp-sheet');
    // v4: a trailing comment is no longer refused; the agents go before it (native-judged in test_symblic_picker_native)
    const cases = [
      ['ask x: Int in 0..9 "Pick." # a note\nensure x = 3 else retry.\n', 2, false],
      ['let t = "a\nb\nask z: Int in 0..9 \\"q\\"\nc"\nensure 1 = 1 else retry.\n', 'let t = "a\nb\n'.length + 2, true],
      ['show 1 + \\\nask x: Int in 0..9 "q"\nensure x = 1 else retry.\n', 'show 1 + \\\n'.length + 2, true],
      ['ask x: Int in 0..9 "Pick."\nensure x = 3 else retry.\n', 2, false],
    ];
    for (const [src, at, disabled] of cases) {
      await page.locator('#sySrc').fill(src);
      await page.locator('#sySrc').evaluate((el, i) => el.setSelectionRange(i, i), at);
      await page.locator('#syPick').click();
      await sheet.locator('.sp-row').first().waitFor();
      await sheet.locator('button[aria-label="Add ollama:qwen3:4b-instruct@node-a"]').click();
      assert.equal(await sheet.locator('button', {hasText: 'Apply to the ask at the cursor'}).isDisabled(), disabled, src);
      if (!disabled && src.includes('#')) {
        await sheet.locator('button', {hasText: 'Apply to the ask at the cursor'}).click();
        assert.equal((await page.locator('#sySrc').inputValue()).split('\n')[0],
          'ask x: Int in 0..9 "Pick." by "ollama:qwen3:4b-instruct@node-a" # a note');
        continue;
      }
      await page.keyboard.press('Escape');
    }
    // whole run: one agent only, never with vote/escalate/search options dropped
    await page.locator('#syPick').click();
    await sheet.locator('.sp-row').first().waitFor();
    await sheet.locator('button[aria-label="Add ollama:deepseek-r1:7b@node-d"]').click();
    await sheet.locator('input[value="vote"]').check();
    assert.equal(await sheet.locator('.sp-text').textContent(), 'by "ollama:deepseek-r1:7b@node-d" with votes=2');
    assert.equal(await sheet.locator('button', {hasText: 'Use for the whole run'}).isDisabled(), true);
    await sheet.locator('input[value="search"]').check();
    assert.equal(await sheet.locator('button', {hasText: 'Use for the whole run'}).isDisabled(), true);
    await sheet.locator('input[value="one"]').check();
    await sheet.locator('button', {hasText: 'Use for the whole run'}).click();
    assert.equal(await page.locator('#syBy').inputValue(), 'ollama:deepseek-r1:7b@node-d');
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

// v4 (review picker-v3 findings 1-6): native statement rules in the page, catalogue order, focus back to the opener
function fixtureV4(calls, {slowFirst = 0, failFirst = false} = {}) {
  let engines = 0, refreshed = false;
  return async (request, url) => {
    calls.push(request.method() + ' ' + url.pathname);
    if (url.pathname === '/api/runner/engines') {
      // Write now loads its discovered selector on entry. The delayed/failing
      // first *sheet* request is the next GET; keep the original race covered.
      const n = ++engines - 1;
      if (failFirst && !refreshed) {
        if (n > 0 && slowFirst) await new Promise(r => setTimeout(r, slowFirst));
        return {status: 500, json: {}};
      }
      if (n === 0) return {json: {engines: ROWS, councils: [], registry: [], methods: []}};
      if (n === 1 && slowFirst) await new Promise(r => setTimeout(r, slowFirst));
      if (n === 1 && failFirst) return {status: 500, json: {}};
      const tag = n === 1 ? 'fake:old' : 'fake:fresh';
      return {json: {engines: [{...ROWS[0], id: tag, spec: tag, title: tag}, ROWS[3]], councils: [], registry: [], methods: []}};
    }
    if (url.pathname === '/api/runner/engines/refresh') {
      if (request.method() === 'POST') { refreshed = true; return {json: {accepted: true, refresh: {state: 'running', active: true}}}; }
      return {json: {refresh: {state: 'done', active: false, completed: 2, total: 2}}};
    }
    const route = url.pathname.replace('/api/automation/symblic/', '');
    if (route === 'meta') return {json: {version: 'fixture', examples: []}};
    if (route === 'check') return {json: {ok: true, plan: [], errors: [], warnings: [], inputs: []}};
    if (route === 'runs') return {json: {runs: []}};
    return undefined;
  };
}
const specs = async (page) => (await page.locator('.sp-sheet .sp-row code').allTextContents()).filter(s => !s.startsWith('council:'));

test('picker v4: an initial catalogue answering after a refresh never replaces the newer one', async () => {
  const calls = [];
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixtureV4(calls, {slowFirst: 3500}), {});
  try {
    await page.locator('#syPick').click();
    await page.locator('.sp-sheet button', {hasText: 'Check the machines'}).click();    // the first GET is still pending
    await page.locator('.sp-sheet .sp-row code', {hasText: 'fake:fresh'}).waitFor({timeout: 8000});
    await page.waitForTimeout(2500);                                                    // the first GET answers at 3.5 s
    assert.deepEqual(await specs(page), ['fake:fresh', 'gemini:flash']);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

test('picker v4: a failed first load says so, the explicit check recovers, and a late failure keeps newer rows', async () => {
  for (const slowFirst of [0, 3500]) {
    const calls = [];
    const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixtureV4(calls, {failFirst: true, slowFirst}), {});
    try {
      await page.locator('#syPick').click();
      if (!slowFirst) await page.locator('.sp-sheet .sp-warn', {hasText: 'Check the machines'}).waitFor();
      await page.locator('.sp-sheet button', {hasText: 'Check the machines'}).click();
      await page.locator('.sp-sheet .sp-row code', {hasText: 'fake:fresh'}).waitFor({timeout: 8000});
      if (slowFirst) await page.waitForTimeout(2500);                                   // the failure arrives late
      assert.deepEqual(await specs(page), ['fake:fresh', 'gemini:flash']);
      assert.equal(await page.locator('.sp-sheet .sp-body > .sp-warn', {hasText: 'did not answer'}).count(), 0);
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  }
});

test('picker v4: closing gives focus back to the control that opened it, and mount callbacks still run', async () => {
  const calls = [];
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixtureV4(calls), {});
  try {
    const focused = () => page.evaluate(() => document.activeElement && document.activeElement.id);
    const rowsShown = () => page.locator('.sp-sheet .sp-row').first().waitFor();
    await page.locator('#syPick').click();
    await rowsShown();
    await page.keyboard.press('Escape');
    assert.equal(await focused(), 'syPick');
    await page.locator('#syPick').click();
    await rowsShown();
    await page.locator('.sp-sheet button[aria-label="Close"]').click();
    assert.equal(await focused(), 'syPick');
    await page.locator('#syPick').click();
    await rowsShown();
    await page.locator('.sp-sheet button[aria-label="Add gemini:flash"]').click();
    await page.locator('.sp-sheet button', {hasText: 'Use for the whole run'}).click();
    assert.equal(await focused(), 'syPick');
    await page.evaluate(() => {
      const b = document.createElement('button');
      b.id = 'mountOpener'; b.textContent = 'Pick agents'; document.body.append(b); b.focus();
      window.__picked = null;
      SymblicPicker.open({onApply: (text) => { window.__picked = text; }});
    });
    await rowsShown();
    await page.locator('.sp-sheet button[aria-label="Add gemini:flash"]').click();
    await page.locator('.sp-sheet button', {hasText: 'Use this'}).click();
    assert.equal(await page.evaluate(() => window.__picked), 'by "gemini:flash"');
    assert.equal(await focused(), 'mountOpener');
    await page.evaluate(() => SymblicPicker.open({opener: document.getElementById('syRun'), onApply: () => {}}));
    await rowsShown();
    await page.keyboard.press('Escape');
    assert.equal(await focused(), 'syRun');
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

test('picker v4: native case, quote and continuation rules in the page; whole-statement group placement and names', async () => {
  const calls = [];
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixtureV4(calls), {});
  try {
    const sheet = page.locator('.sp-sheet');
    const refused = [
      ['ask x: Int "Pick." BY "fake:old".', 2, 'already says who answers'],
      ['ask x: Int "Pick."\n\nby "fake:old".', 2, 'continues on other lines'],
      ["let memo = '''alpha\nask x: Int \"Pick.\"\nomega'''.\nshow memo.", "let memo = '''alpha\n".length + 2, 'Put the cursor on an ask'],
    ];
    for (const [src, at, reason] of refused) {
      await page.locator('#sySrc').fill(src);
      await page.locator('#sySrc').evaluate((el, i) => el.setSelectionRange(i, i), at);
      await page.locator('#syPick').click();
      await sheet.locator('.sp-row').first().waitFor();
      await sheet.locator('button[aria-label="Add gemini:flash"]').click();
      assert.equal(await sheet.locator('button', {hasText: 'Apply to the ask at the cursor'}).isDisabled(), true, src);
      assert.match(await sheet.locator('.sp-why').textContent(), new RegExp(reason));
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#sySrc').inputValue(), src);
    }
    for (const [src, expected] of [
      ['use budget=(\n200000\n).\nshow 1.', 'use budget=(\n200000\n).\ngroup crew = ["fake:fresh", "gemini:flash"].\nshow 1.'],
      ['let crew = 1.\nshow crew.', 'group crew2 = ["fake:fresh", "gemini:flash"].\nlet crew = 1.\nshow crew.'],
    ]) {
      await page.locator('#sySrc').fill(src);
      await page.locator('#syPick').click();
      await sheet.locator('.sp-row').first().waitFor();
      await sheet.locator('button[aria-label="Add fake:old"], button[aria-label="Add fake:fresh"]').first().click();
      await sheet.locator('button[aria-label="Add gemini:flash"]').click();
      await sheet.locator('button', {hasText: 'Insert as a group'}).click();
      assert.equal((await page.locator('#sySrc').inputValue()).replace('fake:old', 'fake:fresh'), expected);
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

after(() => { if (process.env.PICKER_TEXTS_OUT) writeFileSync(process.env.PICKER_TEXTS_OUT, JSON.stringify(texts)); });

const PAPER_V5 = '---\nby: ollama:qwen3:4b-instruct\n---\n# Spider facts\n\nCount walking legs only.\n\n```symblic\nask legs: Int in 0..20 "How many legs?"\nshow legs.\n```\n';
for (const mobile of [false, true]) {
  test(`picker v5: paper retains exact source; copy and run default (${mobile ? 'phone dark' : 'desktop light'})`, async () => {
    const calls = [];
    const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixture(calls), {mobile});
    try {
      await page.evaluate(theme => Studio.setTheme(theme), mobile ? 'dark' : 'light');
      await page.locator('#sySrc').fill(PAPER_V5);
      await page.locator('#sySrc').evaluate(el => el.setSelectionRange(el.value.indexOf('ask legs') + 2, el.value.indexOf('ask legs') + 2));
      await page.evaluate(() => {
        window.__copiedV5 = null;
        Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async text => {window.__copiedV5 = text;}}});
      });
      await page.locator('#syPick').click();
      const sheet = page.locator('.sp-sheet');
      await sheet.locator('.sp-row').first().waitFor();
      await sheet.locator('button[aria-label="Add ollama:qwen3:4b-instruct@node-a"]').click();
      await sheet.locator('button[aria-label="Add gemini:flash"]').click();
      assert.equal(await sheet.locator('button', {hasText: 'Apply to the ask at the cursor'}).isDisabled(), true);
      assert.equal(await sheet.locator('button', {hasText: 'Insert as a group'}).isDisabled(), true);
      assert.match(await sheet.locator('.sp-why').textContent(), /paper.*fenced symblic/s);
      assert.equal(await page.locator('#sySrc').inputValue(), PAPER_V5);
      await sheet.locator('button', {hasText: 'Copy'}).click();
      assert.equal(await page.evaluate(() => window.__copiedV5), await sheet.locator('.sp-text').textContent());
      assert.equal(await noHorizontalScroll(page), true);
      assert.deepEqual(await axe(page), []);
      if (process.env.PICKER_SCREENSHOT_DIR) {
        await page.screenshot({path: `${process.env.PICKER_SCREENSHOT_DIR}/paper-${mobile ? 'phone-dark' : 'desktop-light'}-viewport.png`});
        const geometry = await page.evaluate(() => {
          const rect = document.querySelector('.sp-sheet').getBoundingClientRect();
          return {innerWidth, innerHeight, scrollY, sheet: {left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom},
                  visual: {width: visualViewport.width, height: visualViewport.height, scale: visualViewport.scale}};
        });
        writeFileSync(`${process.env.PICKER_SCREENSHOT_DIR}/geometry-${mobile ? 'phone' : 'desktop'}.json`, JSON.stringify(geometry, null, 2));
      }
      await page.keyboard.press('Escape');
      await page.locator('#syPick').click();
      await sheet.locator('.sp-row').first().waitFor();
      await sheet.locator('button[aria-label="Add ollama:deepseek-r1:7b@node-d"]').click();
      await sheet.locator('button', {hasText: 'Use for the whole run'}).click();
      assert.equal(await page.locator('#syBy').inputValue(), 'ollama:deepseek-r1:7b@node-d');
      assert.equal(await page.locator('#sySrc').inputValue(), PAPER_V5);
      assert.equal(calls.some(c => /\/(run|refresh)$/.test(c)), false);
      assert.deepEqual(errors, []);
    } finally { await context.close(); }
  });
}

test('picker v5: unknown format refuses source edits and mount receives exact normalized format', async () => {
  const calls = [];
  const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixture(calls), {});
  try {
    const program = 'ask x: Int "Choose."\nshow x.\n';
    await page.locator('#sySrc').fill(program);
    await page.locator('#sySrc').evaluate(el => el.setSelectionRange(2, 2));
    await page.evaluate(() => { delete window.SymblicFormat; });
    await page.locator('#syPick').click();
    const sheet = page.locator('.sp-sheet');
    await sheet.locator('.sp-row').first().waitFor();
    await sheet.locator('button[aria-label="Add ollama:qwen3:4b-instruct@node-a"]').click();
    await sheet.locator('button[aria-label="Add gemini:flash"]').click();
    assert.equal(await sheet.locator('button', {hasText: 'Apply to the ask at the cursor'}).isDisabled(), true);
    assert.equal(await sheet.locator('button', {hasText: 'Insert as a group'}).isDisabled(), true);
    assert.match(await sheet.locator('.sp-why').textContent(), /did not say whether/);
    assert.equal(await page.locator('#sySrc').inputValue(), program);
    await page.keyboard.press('Escape');
    for (const format of ['program', 'paper', 'unknown', 'invalid', null, false]) {
      await page.evaluate(value => {
        window.__mountedV5 = null;
        SymblicPicker.open({format: value, onApply: (...args) => {window.__mountedV5 = args;}});
      }, format);
      await sheet.locator('.sp-row').first().waitFor();
      await sheet.locator('button[aria-label="Add ollama:deepseek-r1:7b@node-d"]').click();
      await sheet.locator('button', {hasText: 'Use this'}).click();
      const args = await page.evaluate(() => window.__mountedV5);
      assert.deepEqual(args, ['by "ollama:deepseek-r1:7b@node-d"', ['ollama:deepseek-r1:7b@node-d'], 'one',
                              ['program', 'paper'].includes(format) ? format : 'unknown']);
      assert.equal(await page.locator('#sySrc').inputValue(), program);
    }
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
});
