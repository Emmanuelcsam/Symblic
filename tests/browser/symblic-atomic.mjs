// The Atomic section of the Symblic hub (/symblic/#atomic): the two claims, the measured results table read from
// /symblic/atomic/results.json, and the "Run it yourself" form that starts a spec-sheet build through the existing
// spec/run API and polls it until the page the models wrote can be opened.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {test, launch, open, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

const ROWS = {
  generated: '2026-10-10 15:00',
  rows: [
    {name: 'markdown-ollama-llama3.2-1b-r1', target: 'markdown', mono: false, models: ['ollama:llama3.2:1b'], rep: 1,
      units_total: 13, units_accepted: 13, calls: 41, model_minutes: 22.5,
      harness: {ok: true, cases: 500, pass: 500, fail: 0, fingerprint: 'abc123'}, built_url: '/symblic/atomic/builds/markdown-ollama-llama3.2-1b-r1/markdown.html',
      per_unit: [{unit: 'unit_escapeHtml', status: 'ok', code_sha: 'aaa'}, {unit: 'unit_strongEm', status: 'ok', code_sha: 'bbb'}]},
    {name: 'markdown-mono-ollama-llama3.2-1b-r1', target: 'markdown', mono: true, models: ['ollama:llama3.2:1b'], rep: 1,
      units_total: 1, units_accepted: 0, calls: 8, model_minutes: 30.1, harness: {ok: false, error: 'no built file'}},
    {name: 'markdown-ollama-llama3.2-1b-r2', target: 'markdown', mono: false, models: ['ollama:llama3.2:1b'], rep: 2,
      units_total: 13, units_accepted: 13, calls: 39, model_minutes: 21.0,
      harness: {ok: true, cases: 500, pass: 500, fail: 0, fingerprint: 'abc123'}, built_url: '/symblic/atomic/builds/markdown-ollama-llama3.2-1b-r2/markdown.html',
      per_unit: [{unit: 'unit_escapeHtml', status: 'ok', code_sha: 'aaa'}, {unit: 'unit_strongEm', status: 'ok', code_sha: 'ccc'}]},
  ],
};

const files = {'/symblic/atomic/results.json': {body: JSON.stringify(ROWS), contentType: 'application/json'}};

const boot = async (api = async () => undefined, {mobile = false} = {}) =>
  open(browser, '/symblic/#atomic', api, {mobile, files});

test('renders both claims, the measured table and the repeatability check', async () => {
  const {page, errors} = await boot();
  await page.waitForFunction(() => document.body.textContent.includes('Repeatability (claim 1)'));
  const text = await page.textContent('#stage');
  assert.match(text, /Claim 1: a precise spec makes the result repeatable/);
  assert.match(text, /Claim 2: small local models compose intricate programs/);
  assert.match(text, /llama3\.2 1B/);
  assert.match(text, /13\/13 units/);
  assert.match(text, /no page.*0\/1 units/s);           // the one-shot control that stopped
  assert.match(text, /identical/);                       // two reps, one fingerprint
  assert.match(text, /1 of 2/);                          // one unit byte-identical across the reps
  assert.match(text, /markdown: 2 passing local builds \(1 model\), 0 cloud reference builds, 1 distinct behaviour in all/);
  const open = await page.$$eval('a[href$="/markdown.html"]', (as) => as.map((a) => a.getAttribute('href')));
  assert.deepEqual(open, ['/symblic/atomic/builds/markdown-ollama-llama3.2-1b-r1/markdown.html']);
  assert.deepEqual(errors, []);
});

test('the form starts a build through spec/run and shows the accepted units and the finished page', async () => {
  const calls = [];
  const api = async (request, u) => {
    calls.push(request.method() + ' ' + u.pathname + u.search);
    if (u.pathname === '/api/automation/symblic/spec/run') {
      const body = request.postDataJSON();
      assert.match(body.sheet, /^# markdown\.html/m);
      assert.deepEqual(body.by, ['ollama:llama3.2:1b']);
      assert.deepEqual([body.samples, body.retries, body.rounds], [2, 3, 2]);
      return {json: {id: 'r-atomic'}};
    }
    if (u.pathname === '/api/automation/symblic/run') {
      return {json: {status: 'done', state: {calls: 5, outputs: [{label: 'markdown.html', value: '<!doctype html><title>built</title>'}]},
        trace: [{kind: 'ask', name: 'unit_escapeHtml', status: 'ok', line: 31}, {kind: 'route-attempt', line: 31, status: 'rejected'},
          {kind: 'ask', name: 'unit_strongEm', status: 'ok', line: 60}]}};
    }
    return undefined;
  };
  const {page, errors} = await boot(api);
  await page.waitForSelector('text=Run it yourself');
  await page.click('text=Start the build');
  await page.waitForFunction(() => document.body.textContent.includes('open the page the models wrote'), null, {timeout: 20000});
  const text = await page.textContent('#stage');
  assert.match(text, /Run r-atomic: done, 2 units accepted, 5 model calls so far/);
  assert.match(text, /escapeHtml.*accepted, 1 candidate rejected first/s);
  assert.match(text, /strongEm.*accepted, first candidate/s);
  assert.ok(calls.includes('POST /api/automation/symblic/spec/run'));
  assert.ok(calls.some((c) => c.startsWith('GET /api/automation/symblic/run?id=r-atomic')));
  const links = await page.$$eval('.sh-actions a', (as) => as.map((a) => a.textContent));
  assert.deepEqual(links, ['open the page the models wrote', 'download markdown.html', 'inspect the run']);
  assert.deepEqual(errors, []);
});

test('refuses to start without a model and reports a failed build', async () => {
  const api = async (request, u) => {
    if (u.pathname === '/api/automation/symblic/spec/run') return {json: {id: 'r-fail'}};
    if (u.pathname === '/api/automation/symblic/run') return {json: {status: 'failed', state: {calls: 16, outputs: []}, trace: [{kind: 'ask', name: 'unit_escapeHtml', status: 'failed', line: 31}]}};
    return undefined;
  };
  const {page, errors} = await boot(api);
  await page.waitForSelector('text=Run it yourself');
  for (const box of await page.$$('.chips input:checked')) await box.uncheck();
  await page.click('text=Start the build');
  assert.match(await page.textContent('#stage'), /Tick at least one model/);
  await page.check('.chips input[value="ollama:qwen2.5:0.5b"]');
  await page.uncheck('text=climb the ladder');
  await page.click('text=Start the build');
  await page.waitForFunction(() => document.body.textContent.includes('stopped before the last unit passed'), null, {timeout: 20000});
  assert.match(await page.textContent('#stage'), /escapeHtml.*failed, first candidate/s);
  assert.deepEqual(errors, []);
});

test('with the ladder on, a sheet that fails is retried on the finer sheet with the same models', async () => {
  const posts = [];
  const api = async (request, u) => {
    if (u.pathname === '/api/automation/symblic/spec/run') {
      const body = request.postDataJSON();
      posts.push(body);
      return {json: {id: 'r' + posts.length}};
    }
    if (u.pathname === '/api/automation/symblic/run') {
      const id = new URLSearchParams(u.search).get('id');
      if (id === 'r1') return {json: {status: 'failed', state: {calls: 16, outputs: []}, trace: [{kind: 'ask', name: 'unit_escapeHtml', status: 'ok', line: 31}, {kind: 'ask', name: 'unit_splitBlocks', status: 'failed', line: 158}]}};
      return {json: {status: 'done', state: {calls: 70, outputs: [{label: 'markdown.html', value: '<!doctype html><title>fine</title>'}]}, trace: [{kind: 'ask', name: 'unit_escapeHtml', status: 'ok', line: 17}]}};
    }
    return undefined;
  };
  const {page, errors} = await boot(api);
  await page.waitForSelector('text=Run it yourself');
  await page.click('text=Start the build');
  await page.waitForFunction(() => document.body.textContent.includes('open the page the models wrote'), null, {timeout: 30000});
  const text = await page.textContent('#stage');
  assert.match(text, /decomposed stopped at splitBlocks; trying fine\./);
  assert.equal(posts.length, 2);
  assert.match(posts[0].sheet, /^# markdown\.html/m);
  assert.doesNotMatch(posts[0].sheet, /Answers normalized: yes/);
  assert.match(posts[1].sheet, /Answers normalized: yes/);          // the fine sheet, normalized answers
  assert.deepEqual(posts[1].by, posts[0].by);
  assert.deepEqual(errors, []);
});

test('phone layout has no horizontal scroll and passes accessibility', async () => {
  const {page} = await boot(undefined, {mobile: true});
  await page.waitForFunction(() => document.body.textContent.includes('Repeatability (claim 1)'));
  await noHorizontalScroll(page);
  await axe(page);
});
