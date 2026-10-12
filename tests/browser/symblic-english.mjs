// English authoring journeys with intercepted HTTP only. No real model, server or run is touched.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {test, root, launch, open, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

const SOURCE = 'Remember selected is 7.\nAsk for answer_one as a whole number: "Read selected.".\nUsing only selected.\nShow answer_one.';
const RID = 'abcd1234abcd', OLD = 'ffff1234ffff';
const PAYLOAD = {source: SOURCE, by: 'ollama:qwen3:4b-instruct', max_calls: 32, retries: 2, budget: 12000};
const ATTACK = '<img src=x onerror="window.__englishXss=1">';
const COMPILED = {ok: true, source: 'ask answer_one: Int "Read selected" from selected.',
  statements: [{text: 'Remember selected is 7.'}, {text: ATTACK}], options: {max_calls: 32}};
const DONE = {id: RID, status: 'done', trace: [{kind: 'ask', label: ATTACK, status: 'accepted'}],
  state: {asks: 2, calls: 2, cached: 0, outputs: [
    {value: {kind: 'grid', width: 5, height: 3, x: 0, y: 0, value: 7}},
    {value: {kind: 'grid', width: 5, height: 3, x: 4, y: 2, value: 7}},
  ]}};

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}

async function boot({mobile = false, overrides = {}, saved = {}, url = '/automation-studio/symblic.html#english'} = {}) {
  const fixture = async (request, url) => {
    const route = url.pathname.replace('/api/automation/symblic/', '');
    if (overrides[route]) return overrides[route](request, url);
    if (route === 'meta') return {json: {version: 'test', examples: [], features: {}}};
    if (route === 'english/examples') return {json: {version: 1, examples: {tiny: {title: 'Small grid', source: SOURCE}}}};
    if (route === 'editor/check') {
      const input = request.postDataJSON();
      return {json: {version: 1, language: input.language, source_length_utf16: input.source.length,
        available: true, ok: true, diagnostics: [], check: {ok: true, errors: [], warnings: [], plan: []}}};
    }
    if (route === 'english/check') return {json: COMPILED};
    if (route === 'english/preview') return {json: {ok: true, compiled: COMPILED,
      preview: {status: 'paused', next: {prompt: 'EXACT_TASK_SELECTED_ONLY', schema: {type: 'integer'}}}}};
    if (route === 'english/run') return {json: {id: RID, title: 'English statements'}};
    if (route === 'run') return {json: DONE};
    if (route === 'paper/map') return {json: null};
    if (route === 'runs') return {json: {runs: []}};
    if (route === 'check') return {json: {ok: true, inputs: [], errors: [], warnings: [], plan: []}};
    return undefined;
  };
  const session = await open(browser, url, fixture, {mobile,
    storage: `window.WebSocket = class { close() {} }; sessionStorage.setItem('symblic-english-v1', ${JSON.stringify(JSON.stringify({source: SOURCE, ...saved}))});`});
  await session.page.locator('#sy-en-source').waitFor();
  await session.page.evaluate(theme => Studio.setTheme(theme), mobile ? 'dark' : 'light');
  return session;
}

const posted = s => s.requests.filter(r => r.method === 'POST' && r.path.includes('/symblic/english/'));

test('English running progress follows newly checked frames through completion without redispatch', async () => {
  const outputs = Array.from({length: 7}, (_, index) => ({value: {
    kind: 'grid', width: 20, height: 7, x: 5, y: 6 - index, value: 7
  }}));
  const states = [
    {id: RID, status: 'running', state: {asks: 1, calls: 1, outputs: outputs.slice(0, 1),
      outputs_progress: {partial: true, omitted: 0}}},
    {id: RID, status: 'running', state: {asks: 2, calls: 2, outputs: outputs.slice(0, 2),
      outputs_progress: {partial: true, omitted: 3}}},
    {id: RID, status: 'done', state: {asks: 6, calls: 6, outputs}}
  ];
  let reads = 0;
  const s = await boot({mobile: true, overrides: {'run': () => ({json: states[Math.min(reads++, 2)]})}});
  try {
    await s.page.locator('#sy-en-run').click();
    const frame = s.page.locator('[data-en-frames] [role=img]');
    await frame.waitFor();
    assert.equal(await frame.getAttribute('aria-label'), 'Frame 1: 7 at column 5, row 6');
    await s.page.getByText('Current outputs while this run is in progress.', {exact: true}).waitFor();
    await s.page.waitForFunction(() => document.querySelector('[data-en-frames] [role=img]')?.getAttribute('aria-label') === 'Frame 2: 7 at column 5, row 5');
    assert.match(await s.page.locator('[data-en-run]').textContent(), /3 earlier outputs are omitted from this bounded snapshot/);
    await s.page.waitForFunction(() => document.querySelector('[data-en-status]')?.textContent.startsWith('done'));
    assert.equal(await frame.getAttribute('aria-label'), 'Frame 7: 7 at column 5, row 0');
    assert.equal(await s.page.getByText(/Current outputs while this run is in progress/).count(), 0);
    assert.equal(await s.page.getByText(/earlier outputs are omitted/).count(), 0);
    await s.page.getByRole('button', {name: 'Next frame', exact: true}).click();
    assert.equal(await frame.getAttribute('aria-label'), 'Frame 1: 7 at column 5, row 6');
    assert.equal(reads, 3);
    const writes = s.requests.filter(r => r.method === 'POST' && r.path.startsWith('/api/automation/symblic/') && r.path !== '/api/automation/symblic/editor/check');
    assert.deepEqual(writes.map(r => r.path), ['/api/automation/symblic/english/run']);
    assert.equal(await noHorizontalScroll(s.page), true);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});

test('English saved-run link loads exact frames and original instructions without dispatch', async () => {
  const original = 'Remember original is "' + ATTACK + '".';
  const s = await boot({url: '/automation-studio/symblic.html?english_run=' + RID + '#english',
    saved: {id: OLD}, overrides: {'run': () => ({json: {...DONE,
      meta: {authoring: {document: original}}}})}});
  try {
    await s.page.locator('[data-en-status]').waitFor();
    assert.ok(s.requests.some(r => r.path === '/api/automation/symblic/run' && r.search === '?id=' + RID));
    assert.equal(s.requests.some(r => r.path === '/api/automation/symblic/run' && r.search === '?id=' + OLD), false);
    assert.equal(await s.page.locator('[data-en-frames] [role=img]').getAttribute('aria-label'), 'Frame 1: 7 at column 0, row 0');
    await s.page.getByText('Original instructions for this saved run', {exact: true}).click();
    assert.ok((await s.page.locator('[data-en-run]').textContent()).includes(original));
    assert.equal(await s.page.locator('[data-en-run] img').count(), 0);
    assert.equal(await s.page.getByRole('link', {name: 'Link to saved frames'}).getAttribute('href'), '?english_run=' + RID + '#english');
    await s.page.getByRole('button', {name: 'Next frame', exact: true}).click();
    assert.equal(await s.page.locator('[data-en-frames] [role=img]').getAttribute('aria-label'), 'Frame 2: 7 at column 4, row 2');
    assert.equal(s.requests.filter(r=>r.method==='POST'&&r.path.startsWith('/api/automation/symblic/') && r.path !== '/api/automation/symblic/editor/check').length, 0);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});

test('English malformed saved-run link causes no lookup or dispatch', async () => {
  const s = await boot({url: '/automation-studio/symblic.html?english_run=../../private#english'});
  try {
    await s.page.locator('#sy-en-example option').filter({hasText: 'Small grid'}).waitFor({state: 'attached'});
    assert.equal(s.requests.some(r => r.path === '/api/automation/symblic/run'), false);
    assert.equal(s.requests.filter(r=>r.method==='POST'&&r.path.startsWith('/api/automation/symblic/') && r.path !== '/api/automation/symblic/editor/check').length, 0);
    assert.equal(await s.page.locator('[data-en-status]').count(), 0);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});

test('English failed saved-run link preserves its first frame and mapped failure', async () => {
  const failed = {...DONE, status: 'failed', state: {...DONE.state, error: {line: 17, message: 'Accepted condition was not met.'}},
    meta: {authoring: {document: SOURCE, source_map: [{native_line: 17, line: 3}]}}};
  const s = await boot({url: '/automation-studio/symblic.html?english_run=' + RID + '#english',
    overrides: {'run': () => ({json: failed})}});
  try {
    await s.page.locator('[data-en-status]').waitFor();
    assert.match(await s.page.locator('[data-en-status]').textContent(), /^failed/);
    assert.equal(await s.page.getByRole('alert').textContent(), 'English line 3: Accepted condition was not met.');
    const frame = s.page.locator('[data-en-frames] [role=img]');
    assert.equal(await frame.getAttribute('aria-label'), 'Frame 1: 7 at column 0, row 0');
    await s.page.getByRole('button', {name: 'Next frame', exact: true}).click();
    assert.equal(await frame.getAttribute('aria-label'), 'Frame 2: 7 at column 4, row 2');
    assert.equal(s.requests.filter(r => r.method === 'POST' && r.path.startsWith('/api/automation/symblic/') && r.path !== '/api/automation/symblic/editor/check').length, 0);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});

test('English shipped example titles and real compiled program fit a phone after preview', async () => {
  // Pure compilation: no store, service or provider is started by this fixture.
  const real = JSON.parse(execFileSync(process.env.TEST_PYTHON || 'python3', ['-B', '-c',
    'import json; from symblic.english import compiler as E; source=E.EXAMPLES["falling-number"]["source"]; print(json.dumps({"examples":E.EXAMPLES,"source":source,"compiled":E.compile_source(source,retries=2,max_calls=32,budget=12000)}))'],
  {cwd: root, encoding: 'utf8'}));
  const s = await boot({mobile: true, saved: {source: real.source}, overrides: {
    'english/examples': () => ({json: {version: 1, examples: real.examples}}),
    'english/check': () => ({json: real.compiled}),
    'english/preview': () => ({json: {ok: true, compiled: real.compiled,
      preview: {status: 'paused', next: {prompt: 'EXACT_TASK_SELECTED_ONLY', schema: {type: 'integer'}}}}})
  }});
  try {
    await s.page.locator('#sy-en-example option').filter({hasText: real.examples['falling-number'].title}).waitFor({state: 'attached'});
    assert.equal(await noHorizontalScroll(s.page), true, 'full shipped title fits before check');
    assert.ok(await s.page.evaluate(() => document.documentElement.scrollWidth <= 390), 'phone content stays within its viewport');
    await s.page.locator('#sy-en-check').click();
    await s.page.getByText('How these statements will run', {exact: true}).waitFor();
    await s.page.locator('#sy-en-preview').click();
    await s.page.getByText('Exact next model request', {exact: true}).waitFor();
    await s.page.getByText('Inspect compiled program', {exact: true}).click();
    assert.ok((await s.page.locator('[data-en-reading]').textContent()).includes(real.compiled.source));
    assert.equal(await noHorizontalScroll(s.page), true, 'real compiled program and preview fit');
    assert.ok(await s.page.evaluate(() => document.documentElement.scrollWidth <= 390));
    assert.equal(posted(s).length, 2, 'check and preview only');
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});

for (const mobile of [false, true]) {
  const variant = mobile ? 'phone dark' : 'desktop light';

  test(`English check, exact preview, saved playback and XSS safety (${variant})`, async () => {
    const s = await boot({mobile});
    try {
      const {page} = s;
      await page.locator('#sy-en-check').click();
      await page.getByText('How these statements will run', {exact: true}).waitFor();
      assert.deepEqual(posted(s)[0].body, PAYLOAD);
      assert.equal(await page.locator('[data-en-reading] img').count(), 0);
      assert.match(await page.locator('[data-en-reading]').textContent(), /<img src=x/);
      await page.locator('#sy-en-preview').click();
      await page.getByText('Exact next model request', {exact: true}).waitFor();
      assert.match(await page.locator('[data-en-reading]').textContent(), /EXACT_TASK_SELECTED_ONLY/);
      await page.locator('#sy-en-run').click();
      await page.locator('[data-en-status]').waitFor();
      assert.match(await page.locator('[data-en-status]').textContent(), /done · 2 tasks · 2 model calls/);
      assert.equal(await page.locator('[data-en-run] img').count(), 0);
      assert.equal(await page.evaluate(() => window.__englishXss), undefined);
      const grid = page.locator('[data-en-frames] [role=img]');
      assert.equal(await grid.getAttribute('aria-label'), 'Frame 1: 7 at column 0, row 0');
      assert.equal(await grid.locator('span').count(), 15);
      await page.getByRole('button', {name: 'Next frame', exact: true}).click();
      assert.equal(await grid.getAttribute('aria-label'), 'Frame 2: 7 at column 4, row 2');
      const before = posted(s).length;
      await page.getByRole('button', {name: 'Play frames', exact: true}).click();
      await page.waitForTimeout(720);
      assert.equal(posted(s).length, before, 'saved playback starts no model tasks');
      await page.getByRole('button', {name: 'Pause', exact: true}).click();
      for (const selector of ['#sy-en-source', '#sy-en-by', '#sy-en-calls'])
        assert.ok(await page.locator(selector).evaluate(e => parseFloat(getComputedStyle(e).fontSize) >= 16));
      assert.equal(await noHorizontalScroll(page), true);
      assert.deepEqual(await axe(page), []);
      if (process.env.SYMBLIC_ENGLISH_SHOTS) {
        await mkdir(process.env.SYMBLIC_ENGLISH_SHOTS, {recursive: true});
        await page.screenshot({path: `${process.env.SYMBLIC_ENGLISH_SHOTS}/${mobile ? 'phone-dark' : 'desktop-light'}.png`, fullPage: true});
      }
      assert.deepEqual(s.errors, []);
    } finally { await s.context.close(); }
  });

  test(`English invalid call limits start nothing and zero is retained (${variant})`, async () => {
    const s = await boot({mobile});
    try {
      await s.page.locator('[data-en-panel=limits] > summary').click();
      for (const bad of ['', '-1', '1.5', '10001', 'abc', '3e2', '０']) {
        await s.page.locator('#sy-en-calls').fill(bad);
        await s.page.locator('#sy-en-run').click();
        assert.match(await s.page.getByRole('alert').textContent(), /whole number from 0 to 10000/);
        assert.equal(posted(s).length, 0, `no run for ${JSON.stringify(bad)}`);
      }
      await s.page.locator('#sy-en-calls').fill('0');
      await s.page.locator('#sy-en-run').click();
      await s.page.locator('[data-en-status]').waitFor();
      assert.equal(posted(s)[0].body.max_calls, 0);
      assert.deepEqual(s.errors, []);
    } finally { await s.context.close(); }
  });
}

test('English request completion never takes over another navigation tab', async () => {
  const held = deferred();
  const s = await boot({overrides: {'english/check': () => held.promise}});
  try {
    await s.page.locator('#sy-en-check').click();
    await s.page.evaluate(() => Studio.go('write'));
    await s.page.locator('#sySrc').waitFor();
    held.resolve({json: COMPILED});
    await s.page.waitForTimeout(100);
    assert.equal(await s.page.locator('#sy-en-source').count(), 0);
    assert.equal(await s.page.locator('#sySrc').isVisible(), true);
    await s.page.evaluate(() => Studio.go('english'));
    await s.page.locator('#sy-en-source').waitFor();
    assert.equal(await s.page.locator('#sy-en-check').isEnabled(), true);
    assert.equal(await s.page.locator('#sy-en-source').inputValue(), SOURCE);
    assert.deepEqual(s.errors, []);
  } finally { held.resolve({json: COMPILED}); await s.context.close(); }
});

test('English late examples preserve text typed while they load', async () => {
  const held = deferred();
  const s = await boot({overrides: {'english/examples': () => held.promise}});
  try {
    await s.page.locator('#sy-en-source').fill('My instruction written during loading.');
    await s.page.locator('#sy-en-source').evaluate(e => e.setSelectionRange(3, 8));
    held.resolve({json: {examples: {other: {title: 'Other', source: 'Wrong replacement.'}}}});
    await s.page.locator('#sy-en-example option[value=other]').waitFor({state: 'attached'});
    assert.equal(await s.page.locator('#sy-en-source').inputValue(), 'My instruction written during loading.');
    assert.deepEqual(await s.page.locator('#sy-en-source').evaluate(e => [e === document.activeElement, e.selectionStart, e.selectionEnd]), [true, 3, 8]);
    assert.deepEqual(s.errors, []);
  } finally { held.resolve({json: {examples: {}}}); await s.context.close(); }
});

test('English saved-progress read failures are visible after examples settle', async () => {
  const held = deferred();
  const s = await boot({saved: {id: RID}, overrides: {'run': () => held.promise}});
  try {
    await s.page.locator('#sy-en-example option[value=tiny]').waitFor({state: 'attached'});
    held.resolve({status: 503, json: {error: 'Progress is temporarily unavailable.'}});
    await s.page.getByRole('alert').filter({hasText: /Could not read saved progress/}).waitFor({timeout: 1500});
    assert.match(await s.page.getByRole('alert').textContent(), /temporarily unavailable/);
    assert.deepEqual(s.errors, []);
  } finally { held.resolve({json: DONE}); await s.context.close(); }
});

test('English stale saved-run failure cannot overwrite a newly started run', async () => {
  const old = deferred();
  const s = await boot({saved: {id: OLD}, overrides: {
    'run': (_request, url) => url.searchParams.get('id') === OLD ? old.promise : {json: DONE},
  }});
  try {
    await s.page.locator('#sy-en-example option[value=tiny]').waitFor({state: 'attached'});
    await s.page.locator('#sy-en-run').click();
    await s.page.locator('[data-en-status]').waitFor();
    old.resolve({status: 503, json: {error: 'STALE_OLD_RUN_FAILURE'}});
    await s.page.waitForTimeout(100);
    await s.page.locator('#sy-en-check').click();
    await s.page.getByText('How these statements will run', {exact: true}).waitFor();
    assert.doesNotMatch(await s.page.locator('.sy-english').textContent(), /STALE_OLD_RUN_FAILURE/);
    assert.match(await s.page.locator('[data-en-status]').textContent(), /done · 2 tasks/);
    assert.deepEqual(s.errors, []);
  } finally { old.resolve({json: DONE}); await s.context.close(); }
});

test('English missing server capability produces a visible restart explanation', async () => {
  const s = await boot({overrides: {'english/examples': () => ({status: 503, json: {error: 'English statements need the server update and restart.'}})}});
  try {
    await s.page.getByRole('alert').waitFor();
    assert.match(await s.page.getByRole('alert').textContent(), /server update and restart/);
    assert.equal(posted(s).length, 0);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});

test('English full-run button opens the exact saved native record and can resume it', async () => {
  const s = await boot();
  try {
    await s.page.locator('#sy-en-run').click();
    await s.page.locator('[data-en-status]').waitFor();
    await s.page.getByRole('button', {name: 'Open full run', exact: true}).click();
    await s.page.locator('#syResume').waitFor();
    assert.equal(await s.page.evaluate(() => location.hash), '#runs');
    assert.equal(await s.page.locator('#sy-en-source').count(), 0);
    assert.ok(s.requests.some(r => r.path === '/api/automation/symblic/run' && r.search === '?id=' + RID));
    await s.page.locator('#syResume').click();
    await s.page.waitForFunction(() => document.querySelector('#toast')?.textContent.includes('Resumed'));
    assert.ok(s.requests.some(r => r.method === 'POST' && r.path === '/api/automation/symblic/resume' && r.body.id === RID));
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});
