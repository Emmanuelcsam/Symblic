// Isolated Workcards journeys. Every request is fulfilled locally; no server,
// model, live run or browser daemon is reached. The exported journey also runs
// through the pinned Playwright CLI with an explicit staging assetRoot.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const ORIGIN = 'http://127.0.0.1:18769';
const RID = 'abcd1234abcd';
const MODELS = ['ollama:llama3.2:1b@node-a', 'ollama:qwen2.5:0.5b@node-i'];
const REQUEST = {title: 'One function <img src=x onerror="window.__stepsXss=1">', steps: [
  {name: 'twice', instruction: 'Multiply x by two.', parameters: [{name: 'x', type: 'Int'}], returns: 'Int',
    uses: [], choices: ['x + 2', 'x * 2'], checks: ['twice(3) = 6']},
  {name: 'next', instruction: 'Add one to twice(x).', parameters: [{name: 'x', type: 'Int'}], returns: 'Int',
    uses: ['twice'], choices: ['twice(x) + 1', 'twice(x) - 1'], checks: ['next(3) = 7']}
], final_checks: ['next(7) = 15'], program: 'show next(10).'};
const SOURCE = 'use profile=verified, context=none.\ngiven brick_card_0: Any.\nask brick_choice_0: one of {"x + 2", "x * 2"} "Multiply x by two" from brick_card_0.\nshow brick_choice_0.\n';
const FALLBACK_SOURCE = SOURCE.replace('from brick_card_0.', 'from brick_card_0 with fallback_choices=["x + 2", "x * 2"].');
const COMPILED = {source: SOURCE, inputs: {_steps_request: REQUEST, _steps_settings: {by: MODELS[0], retries: 2, context_budget: 12000}, brick_card_0: {signature: 'twice(x: Int) -> Int'}},
  options: {profile: 'verified', max_calls: 6, max_asks: 6, parallel: 1, determine: false, solve: false,
    constructor: 'off', side_effects: false, execution_pins: {sha256: 'fixture-exact-pins'}}, assurance: 'Fixture checked construction.'};
const ARTIFACT = {source: 'use profile=verified.\nfunction twice(x: Int) -> Int = x * 2.\nfunction next(x: Int) -> Int = twice(x) + 1.\nassert next(7) = 15.\nshow next(10).\n', inputs: {},
  status: 'prepared', execution: 'not_run', options: {profile: 'verified', max_calls: 0, max_asks: 0, side_effects: false, constructor: 'off'}};
const ORIGIN_SUMMARY = '1 functions selected by the model; 1 completed by finite checks (2 engine trials).';
const TYPES = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2'};

export async function runStepsJourney(browser, {mobile = false, assetRoot = root, screenshotDir = null} = {}) {
  const context = await browser.newContext({viewport: mobile ? {width: 390, height: 844} : {width: 1400, height: 1000},
    isMobile: mobile, hasTouch: mobile, acceptDownloads: true, colorScheme: mobile ? 'dark' : 'light'});
  const calls = [], errors = [];
  let compileGate = null;
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== ORIGIN) return route.abort();
    if (url.pathname.startsWith('/api/')) {
      let body = null;
      try { body = request.postDataJSON(); } catch (_) { /* GET */ }
      calls.push({path: url.pathname, method: request.method(), body});
      if (url.pathname === '/api/runner/engines') return route.fulfill({json: {engines: MODELS.map(spec => ({spec, id: spec, title: spec, engine: 'ollama', model: spec.split(':').slice(1).join(':'), kind: 'local', typed_ask: true, selectable: true, ready: true})), errors: [], councils: []}});
      if (url.pathname.endsWith('/workcards/steps/compile')) {
        if (compileGate) await compileGate;
        const compiled = JSON.parse(JSON.stringify(COMPILED));
        compiled.source = body.finite_fallback ? FALLBACK_SOURCE : SOURCE;
        compiled.inputs._steps_request = body.request;
        compiled.inputs._steps_settings = {by: body.by, retries: body.retries, context_budget: 12000};
        if (body.finite_fallback) compiled.inputs._steps_settings.finite_fallback = true;
        return route.fulfill({json: compiled});
      }
      if (url.pathname.endsWith('/workcards/steps/result')) {
        if (body.id === RID) return route.fulfill({json: {id: RID, status: 'done', accepted: true, choices: {twice: 2, next: 1},
          selection_origins: {twice: 'finite_fallback', next: 'model'}, model_selected_steps: 1, finite_selected_steps: 1, finite_trials: 2,
          artifact: ARTIFACT, assurance: 'Passed authored checks; independent inputs remain untested.'}});
        if (body.id === '111111111111') return route.fulfill({json: {id: body.id, status: 'failed', accepted: false}});
        return route.fulfill({status: 400, json: {error: 'No such run.'}});
      }
      if (url.pathname.endsWith('/editor/check')) return route.fulfill({json: {version: 1, language: body.language,
        source_length_utf16: body.source.length, available: true, ok: true, diagnostics: [],
        check: {ok: true, errors: [], warnings: [], plan: []}}});
      if (url.pathname.endsWith('/check')) return route.fulfill({json: {ok: true, errors: [], warnings: [], plan: []}});
      if (url.pathname.endsWith('/meta')) return route.fulfill({json: {version: 'fixture', examples: [], features: {}}});
      if (url.pathname.endsWith('/runs')) return route.fulfill({json: {runs: []}});
      if (url.pathname.endsWith('/run') && request.method() === 'POST') return route.fulfill({json: {id: '000000000001'}});
      return route.fulfill({json: {}});
    }
    if (url.pathname === '/automation-studio/symblic-steps-parcel.json') return route.fulfill({json: REQUEST});
    const relative = url.pathname.replace(/^\//, '');
    for (const base of [assetRoot, root]) {
      const filename = path.resolve(base, relative);
      if (!filename.startsWith(path.resolve(base) + path.sep)) return route.fulfill({status: 403});
      try { return await route.fulfill({body: await fs.readFile(filename), contentType: TYPES[path.extname(filename)] || 'application/octet-stream'}); }
      catch (_) { /* Fall through from staged assets to unchanged checkout assets. */ }
    }
    return route.fulfill({status: 404, body: ''});
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  const button = name => page.getByRole('button', {name, exact: true});
  const fallback = () => page.getByRole('checkbox', {name: 'Let the engine try the finite menu after rejected model attempts', exact: true});
  const verifyOrigins = async () => {
    await page.getByText(ORIGIN_SUMMARY, {exact: true}).waitFor();
    await page.getByText('Who selected each function?', {exact: true}).click();
    await page.getByText('twice: engine finite completion', {exact: true}).waitFor();
    await page.getByText('next: model proposal', {exact: true}).waitFor();
  };
  const prepare = async () => {
    await button('Prepare checked steps').click();
    await button('Open construction in Write').waitFor();
  };
  const openEditor = async () => {
    const editor = page.locator('#sy-steps-request');
    if (!await editor.isVisible()) await page.getByText('Edit instructions, choices and checks', {exact: true}).click();
    return editor;
  };
  try {
    await page.goto(ORIGIN + '/automation-studio/symblic.html#workcards');
    await page.evaluate(theme => Studio.setTheme(theme), mobile ? 'dark' : 'light');
    await button('Build one step at a time').click();
    assert.equal(await fallback().isChecked(), false, 'finite completion is opt-in');
    assert.equal(await button('Prepare checked steps').isDisabled(), true);
    await (await openEditor()).fill(JSON.stringify(REQUEST));
    assert.equal(await button('Prepare checked steps').isEnabled(), true, 'manual JSON entry enables preparation');
    await (await openEditor()).fill('   ');
    assert.equal(await button('Prepare checked steps').isDisabled(), true, 'empty editor disables preparation');
    await button('Load parcel program example').click();
    await page.locator('[data-steps-outline]').waitFor();
    assert.equal(await page.locator('.sy-workcards img').count(), 0, 'instruction/title markup stays text');
    await page.getByLabel('Step worker model', {exact: true}).selectOption(MODELS[0]);
    await prepare();
    const posted = calls.filter(row => row.path.endsWith('/steps/compile')).at(-1).body;
    assert.deepEqual(posted, {request: REQUEST, by: MODELS[0], retries: 2, finite_fallback: false});
    await button('Open construction in Write').click();
    assert.equal(await page.locator('#sySrc').inputValue(), SOURCE);
    const task = await page.evaluate(() => JSON.parse(sessionStorage.getItem('symblic-v3-task') || 'null'));
    assert.ok(task, 'Write preserves the prepared task');
    assert.deepEqual(task.options, COMPILED.options);
    assert.deepEqual(JSON.parse(task.inputs._steps_request), REQUEST);
    await page.evaluate(() => Studio.go('workcards'));
    await button('Open construction in Write').waitFor();
    await fallback().check();
    assert.equal(await button('Open construction in Write').count(), 0, 'opting in removes stale prepared source');
    await prepare();
    assert.deepEqual(calls.filter(row => row.path.endsWith('/steps/compile')).at(-1).body,
      {request: REQUEST, by: MODELS[0], retries: 2, finite_fallback: true});
    await button('Open construction in Write').click();
    assert.equal(await page.locator('#sySrc').inputValue(), FALLBACK_SOURCE);
    const fallbackTask = await page.evaluate(() => JSON.parse(sessionStorage.getItem('symblic-v3-task')));
    assert.deepEqual(fallbackTask.options, COMPILED.options);
    assert.equal(JSON.parse(fallbackTask.inputs._steps_settings).finite_fallback, true);
    await page.evaluate(() => Studio.go('workcards'));
    await button('Open construction in Write').waitFor();
    assert.equal(await fallback().isChecked(), true);
    await fallback().uncheck();
    assert.equal(await button('Open construction in Write').count(), 0, 'opting out removes stale fallback source');
    await prepare();
    assert.equal(calls.filter(row => row.path.endsWith('/steps/compile')).at(-1).body.finite_fallback, false);
    await page.getByLabel('Step worker model', {exact: true}).selectOption(MODELS[1]);
    assert.equal(await button('Open construction in Write').count(), 0, 'model change removes stale prepared action');
    await prepare();
    await (await openEditor()).fill(JSON.stringify({...REQUEST, title: 'Changed objective'}));
    assert.equal(await button('Open construction in Write').count(), 0, 'editing objective removes stale prepared action immediately');
    await prepare();
    await page.getByLabel('Maximum corrections for each step').selectOption('1');
    assert.equal(await button('Open construction in Write').count(), 0, 'retry change invalidates prepared source');
    await prepare();
    let release;
    compileGate = new Promise(resolve => { release = resolve; });
    await button('Prepare checked steps').click();
    assert.equal(await button('Open construction in Write').isDisabled(), true, 'old prepared action disabled during request');
    assert.equal(await page.locator('#sy-steps-run').isDisabled(), true);
    assert.equal(await fallback().isDisabled(), true, 'fallback policy cannot change during preparation');
    release(); compileGate = null;
    await button('Prepare checked steps').waitFor();
    await page.locator('#sy-steps-run').fill('  ' + RID + '  ');
    await button('Get checked program').click();
    await button('Open finished program in Write').waitFor();
    assert.deepEqual(calls.filter(row => row.path.endsWith('/steps/result')).at(-1).body, {id: RID});
    await verifyOrigins();
    await fallback().check();
    assert.equal(await button('Open finished program in Write').count(), 0, 'policy changes invalidate stale recovered artifact');
    assert.equal(await page.getByText(ORIGIN_SUMMARY, {exact: true}).count(), 0, 'policy changes remove stale attribution');
    await button('Get checked program').click();
    await button('Open finished program in Write').waitFor();
    await verifyOrigins();
    await button('Open finished program in Write').click();
    assert.equal(await page.locator('#sySrc').inputValue(), ARTIFACT.source);
    const artifactTask = await page.evaluate(() => JSON.parse(sessionStorage.getItem('symblic-v3-task')));
    assert.deepEqual(artifactTask.options, ARTIFACT.options);
    await page.evaluate(() => Studio.go('workcards'));
    await button('Download .sym file').waitFor();
    const downloadPromise = page.waitForEvent('download');
    await button('Download .sym file').click();
    const download = await downloadPromise;
    assert.equal(await fs.readFile(await download.path(), 'utf8'), ARTIFACT.source);
    await page.locator('#sy-steps-run').fill('111111111111');
    assert.equal(await button('Open finished program in Write').count(), 0, 'new ID removes old artifact actions immediately');
    assert.equal(await button('Download .sym file').count(), 0);
    assert.equal(await page.getByText(ORIGIN_SUMMARY, {exact: true}).count(), 0, 'new ID removes old attribution');
    await button('Get checked program').click();
    await page.getByRole('alert').waitFor();
    assert.match(await page.getByRole('alert').textContent(), /failed/);
    assert.equal(await button('Download .sym file').count(), 0);
    await page.locator('#sy-steps-run').fill('../../private');
    await button('Get checked program').click();
    await page.getByRole('alert').waitFor();
    assert.match(await page.getByRole('alert').textContent(), /No such run/);
    await page.reload();
    await button('Build one step at a time').click();
    assert.equal(await fallback().isChecked(), false, 'reload does not silently opt in');
    await page.locator('#sy-steps-run').fill(RID);
    await button('Get checked program').click();
    await button('Open finished program in Write').waitFor();
    await verifyOrigins();
    assert.equal(await page.locator('#sy-steps-request').inputValue(), '', 'recovery does not require editor request');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'no horizontal overflow');
    assert.equal(await page.locator('#sy-steps-run').evaluate(node => parseFloat(getComputedStyle(node).fontSize) >= 16), true);
    assert.deepEqual(errors, []);
    assert.equal(calls.some(row => row.path.endsWith('/run') && row.method === 'POST'), false, 'opening/downloading never dispatches a run');
    assert.equal(calls.some(row => row.method === 'POST' && !row.path.endsWith('/check') && !row.path.includes('/workcards/steps/') && row.path !== '/api/perf/beacon'), false);
    if (screenshotDir) {
      await fs.mkdir(screenshotDir, {recursive: true});
      await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
      await page.screenshot({path: path.join(screenshotDir, mobile ? 'steps-phone-dark.png' : 'steps-desktop-light.png'), fullPage: true, animations: 'disabled'});
    }
    return {variant: mobile ? 'phone dark touch' : 'desktop light', prepared_handoff: true, artifact_handoff: true,
      finite_fallback_default_off: true, finite_fallback_payload: true, finite_fallback_handoff: true,
      finite_fallback_invalidates_stale_state: true, selection_origins_visible: true,
      stale_actions_invalidated: true, recovery_after_reload: true, download_exact: true, page_errors: errors,
      model_calls: 0, live_run_requests: 0, browser_requests_intercepted: calls.length};
  } finally { await context.close(); }
}

// Direct `node --test tests/browser/symblic-steps.mjs` remains compatible with
// the repository harness. Importing for the pinned CLI only exposes the driver.
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const {before, after} = await import('node:test');
  const {test, launch} = await import('./host-harness.mjs');
  let browser;
  before(async () => { browser = await launch(); });
  after(async () => { await browser?.close(); });
  for (const mobile of [false, true]) test('checked steps ' + (mobile ? 'phone dark' : 'desktop light'), async () => {
    await runStepsJourney(browser, {mobile});
  });
}
