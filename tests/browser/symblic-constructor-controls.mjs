// Write-page checked-construction controls: off parity, exact enabled options (zero included), invalid budgets,
// paper and bound-task guards, a missing or old meta marker, a visible zero-fallback failure, help and layout.
// Mocked APIs only (no server, store, worker, solver or model); desktop light and phone dark.
// SYMBLIC_PAGE_PREIMAGE=<path to the pre-change symblic-page.js> also replays the off journeys on that file and
// requires byte-identical Run request bodies.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test, launch, open, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

const PROGRAM = 'program Next.\n\ngiven base: Int = 10.\nask next: Int "Construct the next integer.".\nensure next = base + 1 else retry.\nshow next.\n';
const PAPER = '---\ntitle: Next\n---\n\n# Next\n\n```symblic\nask next: Int "Pick an integer.".\nshow next.\n```\n';
const MARKER = {version: 1, modes: ['off', 'linear_diagnose', 'linear'], requires: {determine: false, solve: false}, max_calls: [0, 10000]};
const FAILED = {id: 'aaaaaaaaaaaa', status: 'failed', source: PROGRAM, meta: {title: 'Next', by: 'claude:haiku', options: {}},
  state: {status: 'failed', asks: 1, calls: 0, error: {line: 4, col: 0, kind: 'budget',
    message: 'the program exhausted its model-call budget (0)'}}, trace: [], artifacts: []};
const PREIMAGE = process.env.SYMBLIC_PAGE_PREIMAGE ? readFileSync(process.env.SYMBLIC_PAGE_PREIMAGE, 'utf8') : null;

function fixture(calls, {features = {strict_model_pins: true, constructor_options: MARKER}, metaStatus = 200} = {}) {
  return async (request, url) => {
    const route = url.pathname.replace('/api/automation/symblic/', '');
    calls.push(route);
    if (route === 'meta') return metaStatus === 200
      ? {json: {version: 'fixture', examples: [], ...(features === null ? {} : {features})}}
      : {status: metaStatus, json: {error: 'meta failed'}};
    if (route === 'editor/check') return {status: 404, json: {error: 'Older fixture uses native check'}};
    if (route === 'paper/check') return {json: {ok: true, plan: [], errors: [], warnings: [], inputs: []}};
    if (route === 'check') return {json: {ok: true, name: 'Next', plan: [], errors: [], warnings: [], inputs: []}};
    if (route === 'runs') return {json: {runs: [{id: FAILED.id, title: 'Next', status: 'failed', by: 'claude:haiku', calls: 0}]}};
    if (route === 'run' && request.method() === 'GET') return {json: FAILED};
    if (route === 'run' || route === 'paper/run') return {json: {id: FAILED.id, title: 'Next'}};
    if (route === 'paper/map') return {json: null};
    return undefined;
  };
}

// storage: draft program plus optional saved constructor choice and bound task, as the page itself stores them
function storage({source = PROGRAM, ctor = null, task = null} = {}) {
  return `(() => { try {
    localStorage.setItem('symblic-v2-draft', ${JSON.stringify(source)});
    localStorage.setItem('symblic-v2-by', 'claude:haiku');
    ${ctor ? `sessionStorage.setItem('symblic-v4-constructor', ${JSON.stringify(JSON.stringify(ctor))});` : ''}
    ${task ? `sessionStorage.setItem('symblic-v3-task', ${JSON.stringify(JSON.stringify({source, inputs: {}, options: task}))});` : ''}
  } catch (_) {} })();`;
}

async function boot(opts = {}, {mobile = false, page: pageFile = null, fixtureOpts = {}} = {}) {
  const calls = [];
  const files = pageFile ? {'/automation-studio/symblic-page.js': {body: pageFile, contentType: 'text/javascript'}} : null;
  const session = await open(browser, '/automation-studio/symblic.html#write', fixture(calls, fixtureOpts),
    {mobile, storage: storage(opts), files});
  const bodies = [];
  session.page.on('request', (r) => { if (r.method() === 'POST' && /\/symblic\/(paper\/)?run$/.test(new URL(r.url()).pathname)) bodies.push({path: new URL(r.url()).pathname, raw: r.postData()}); });
  await session.page.evaluate((theme) => Studio.setTheme(theme), mobile ? 'dark' : 'light');
  await session.page.locator('#syRun').waitFor();
  await session.page.locator('.sy-native-settings > summary').click();
  await session.page.waitForFunction(() => document.querySelector('#sySrc')?.value.length > 0);
  if (!pageFile) await session.page.locator('#syCtorOn').waitFor({state: 'attached'});
  await session.page.waitForTimeout(150);                          // meta + check settle (mocked, immediate)
  return {...session, calls, bodies};
}

async function run(s) {
  const before = s.bodies.length;
  await s.page.locator('#syRun').click();
  await s.page.waitForTimeout(250);
  return s.bodies.slice(before);
}

async function openCtor(page) {
  await page.locator('#syCtorBox > summary').click();
}

// a paper's check result names nothing here, so its run title is empty (both before and after the change)
const offBody = (source, options) => JSON.stringify({source, inputs: {}, by: 'claude:haiku', title: source === PAPER ? '' : 'Next', options});

for (const mobile of [false, true]) {
  const tag = mobile ? 'phone dark' : 'desktop light';

  test(`constructor controls: off payload is the exact pre-change body (${tag})`, async () => {
    const cases = [
      {name: 'program', opts: {}, path: '/api/automation/symblic/run', body: offBody(PROGRAM, {side_effects: false})},
      {name: 'program, no marker', opts: {}, fixtureOpts: {features: {strict_model_pins: true}}, path: '/api/automation/symblic/run', body: offBody(PROGRAM, {side_effects: false})},
      {name: 'paper', opts: {source: PAPER}, path: '/api/automation/symblic/paper/run', body: offBody(PAPER, {side_effects: false})},
      {name: 'bound task', opts: {task: {profile: 'verified', max_calls: 4, parallel: 1}}, path: '/api/automation/symblic/run',
        body: offBody(PROGRAM, {profile: 'verified', max_calls: 4, parallel: 1, side_effects: false})},
    ];
    for (const c of cases) {
      const variants = [['candidate', null], ...(PREIMAGE ? [['preimage', PREIMAGE]] : [])];
      for (const [label, file] of variants) {
        const s = await boot(c.opts, {mobile, page: file, fixtureOpts: c.fixtureOpts});
        try {
          const sent = await run(s);
          assert.equal(sent.length, 1, `${c.name} ${label}: one run request`);
          assert.equal(sent[0].path, c.path, `${c.name} ${label}: route`);
          assert.equal(sent[0].raw, c.body, `${c.name} ${label}: byte-identical body`);
          assert.deepEqual(s.errors, []);
        } finally { await s.context.close(); }
      }
    }
  });

  test(`constructor controls: enabled modes send the exact contract, zero included (${tag})`, async () => {
    for (const [mode, calls] of [['linear', '0'], ['linear_diagnose', '0'], ['linear', '12'], ['linear_diagnose', '10000']]) {
      const s = await boot({}, {mobile});
      try {
        const {page} = s;
        await openCtor(page);
        await page.locator('#syCtorOn').check();
        await page.locator('#syCtorAdv > summary').click();
        assert.equal(await page.locator('#syCtorCalls').inputValue(), '0', 'the visible default budget is zero');
        await page.locator('#syCtorMode').selectOption(mode);
        await page.locator('#syCtorCalls').fill(calls);
        for (const id of ['#syCtorMode', '#syCtorCalls']) {
          assert.ok(await page.locator(id).evaluate((el) => parseFloat(getComputedStyle(el).fontSize) >= 16), id + ' is at least 16px');
          assert.equal(await page.locator(id).isVisible(), true);
        }
        assert.equal(await page.locator('#syCtorWhy').isHidden(), true, 'no blocking reason for a native program');
        assert.equal(await noHorizontalScroll(page), true);
        assert.deepEqual(await axe(page), []);
        if (process.env.SYMBLIC_CONTROL_SHOTS && mode === 'linear' && calls === '0')
          await page.screenshot({path: process.env.SYMBLIC_CONTROL_SHOTS + '/' + (mobile ? 'phone-dark' : 'desktop-light') + '.png'});
        const sent = await run(s);
        assert.equal(sent.length, 1);
        assert.equal(sent[0].path, '/api/automation/symblic/run');
        assert.equal(sent[0].raw, offBody(PROGRAM, {side_effects: false, constructor: mode, determine: false, solve: false, max_calls: Number(calls)}));
        assert.deepEqual(s.errors, []);
      } finally { await s.context.close(); }
    }
  });

  test(`constructor controls: invalid budgets start nothing and say why (${tag})`, async () => {
    const s = await boot({ctor: {on: true, mode: 'linear', calls: '0'}}, {mobile});
    try {
      const {page} = s;
      for (const bad of ['', '-1', '1.5', '10001', 'abc', '3e2', '1 2', '０']) {
        await page.locator('#syCtorAdv').evaluate((d) => { d.open = true; });
        await page.locator('#syCtorCalls').fill(bad);
        assert.equal(await page.locator('#syCtorErr').textContent(), 'Enter a whole number from 0 to 10000.', `error for ${JSON.stringify(bad)}`);
        assert.equal(await page.locator('#syCtorCalls').getAttribute('aria-invalid'), 'true');
        const sent = await run(s);
        assert.equal(sent.length, 0, `no run for ${JSON.stringify(bad)}`);
        assert.match(await page.locator('#toast').textContent(), /whole number from 0 to 10000; no run was started/);
      }
      await page.locator('#syCtorCalls').fill('3');
      assert.equal(await page.locator('#syCtorErr').textContent(), '');
      const sent = await run(s);
      assert.equal(sent[0].raw, offBody(PROGRAM, {side_effects: false, constructor: 'linear', determine: false, solve: false, max_calls: 3}));
      assert.deepEqual(s.errors, []);
    } finally { await s.context.close(); }
  });

  test(`constructor controls: paper keeps its ordinary path with a reason (${tag})`, async () => {
    const s = await boot({source: PAPER, ctor: {on: true, mode: 'linear', calls: '0'}}, {mobile});
    try {
      const {page} = s;
      assert.equal(await page.locator('#syCtorOn').isDisabled(), true);
      assert.equal(await page.locator('#syCtorOn').isChecked(), false);
      assert.match(await page.locator('#syCtorWhy').textContent(), /apply to native programs.*paper forwarding is verified/);
      assert.equal(await page.locator('#syCtorCalls').isDisabled(), true);
      const sent = await run(s);
      assert.equal(sent[0].path, '/api/automation/symblic/paper/run');
      assert.equal(sent[0].raw, offBody(PAPER, {side_effects: false}));
      assert.match(await page.locator('#toast').textContent(), /without checked construction: it applies to native programs/);
      // typing the editor back into a native program restores the saved selection
      await page.evaluate(() => Studio.go('write'));
      await page.locator('#sySrc').fill(PROGRAM);
      assert.equal(await page.locator('#syCtorOn').isDisabled(), false);
      assert.equal(await page.locator('#syCtorOn').isChecked(), true);
      assert.deepEqual(s.errors, []);
    } finally { await s.context.close(); }
  });

  test(`constructor controls: bound and delegated task policies go out unchanged (${tag})`, async () => {
    const tasks = [
      {profile: 'verified', max_calls: 4, parallel: 1},                                          // Logic proof task
      {profile: 'verified', max_calls: 2, parallel: 1, side_effects: false,                      // delegated contract task
        execution_pins: {version: 1, kernel_id: 'fixture', source_sha256: 'a'.repeat(64)}, by: 'fake:a'},
    ];
    tasks.push({profile: 'verified', constructor: 'linear', determine: false, solve: false, max_calls: 0});
    for (const task of tasks) {
      const s = await boot({task, ctor: {on: true, mode: 'linear', calls: '0'}}, {mobile});
      try {
        const {page} = s;
        assert.equal(await page.locator('#syCtorOn').isDisabled(), true);
        assert.match(await page.locator('#syCtorWhy').textContent(), /its own run policy/);
        const sent = await run(s);
        const body = JSON.parse(sent[0].raw);
        assert.deepEqual(body.options, {...task, side_effects: false});
        if (!task.constructor) assert.equal(Object.keys(body.options).some((k) => k.startsWith('constructor') || k === 'solve' || k === 'determine'), false);
        else assert.equal(body.options.constructor, task.constructor, 'the prepared construction setting is retained');
        assert.equal(body.options.max_calls, task.max_calls, 'the bound call budget is not weakened');
        assert.deepEqual(s.errors, []);
      } finally { await s.context.close(); }
    }
  });

  test(`constructor controls: missing or failed meta marker blocks a saved policy (${tag})`, async () => {
    for (const fixtureOpts of [{features: {strict_model_pins: true}}, {features: null}, {metaStatus: 500},
      {features: {constructor_options: {version: 2, modes: ['off', 'linear']}}}]) {
      // nothing saved: the control is off and disabled with the reason; Run is the ordinary body
      let s = await boot({}, {mobile, fixtureOpts});
      try {
        assert.equal(await s.page.locator('#syCtorOn').isDisabled(), true);
        assert.match(await s.page.locator('#syCtorWhy').textContent(), /does not report checked-construction support/);
        const sent = await run(s);
        assert.equal(sent[0].raw, offBody(PROGRAM, {side_effects: false}));
      } finally { await s.context.close(); }
      // a saved selection stays visible and blocks Run until cleared; it is never silently dropped
      s = await boot({ctor: {on: true, mode: 'linear', calls: '0'}}, {mobile, fixtureOpts});
      try {
        const {page} = s;
        assert.equal(await page.locator('#syCtorOn').isDisabled(), false);
        assert.equal(await page.locator('#syCtorOn').isChecked(), true);
        assert.equal(await page.locator('#syCtorBox').evaluate((d) => d.open), true);
        assert.equal((await run(s)).length, 0);
        assert.match(await page.locator('#toast').textContent(), /needs a server update.*no run was started/);
        await page.locator('#syCtorOn').uncheck();
        assert.equal(await page.locator('#syCtorOn').isDisabled(), true);
        const sent = await run(s);
        assert.equal(sent[0].raw, offBody(PROGRAM, {side_effects: false}));
        assert.deepEqual(s.errors, []);
      } finally { await s.context.close(); }
      // a paper with a saved selection is not blocked by the missing marker: the policy never applies to it
      s = await boot({source: PAPER, ctor: {on: true, mode: 'linear', calls: '0'}}, {mobile, fixtureOpts});
      try {
        assert.match(await s.page.locator('#syCtorWhy').textContent(), /apply to native programs/);
        const sent = await run(s);
        assert.equal(sent[0].raw, offBody(PAPER, {side_effects: false}));
      } finally { await s.context.close(); }
    }
  });

  test(`constructor controls: a zero-fallback failure stays visibly failed; help explains (${tag})`, async () => {
    const s = await boot({ctor: {on: true, mode: 'linear', calls: '0'}}, {mobile});
    try {
      const {page} = s;
      const sent = await run(s);
      assert.equal(JSON.parse(sent[0].raw).options.max_calls, 0);
      await page.locator('.stat .big', {hasText: 'failed'}).waitFor();
      assert.match(await page.locator('.card', {hasText: 'model-call budget'}).textContent(), /exhausted its model-call budget \(0\)/);
      // help explain mode on the new control
      await page.evaluate(() => Studio.go('write'));
      await page.locator('#syCtorOn').waitFor({state: 'attached'});
      await page.locator('.sh-fab').click();
      await page.locator('.sh-hint').waitFor();
      await page.locator('#syCtorOn').click({force: true});
      await page.locator('.sh-panel h2', {hasText: 'Checked construction'}).waitFor();
      await page.waitForTimeout(200);
      assert.equal(s.bodies.length, 1, 'explain mode starts nothing');
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#syCtorOn').isChecked(), true, 'explain mode does not toggle the setting');
      assert.deepEqual(s.errors, []);
    } finally { await s.context.close(); }
  });
}
