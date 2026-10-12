// Static beta gallery: renders from embedded data only, players step without model calls.
// No API is called by the page; the fixture answers anything studio.js may ask with {}.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {test, launch, open, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

const boot = async ({mobile = false} = {}) =>
  open(browser, '/symblic/beta.html', async () => undefined, {mobile});   // symblic-hub/beta.html since 2026-10-10

test('renders the record from embedded data', async () => {
  const {page} = await boot();
  assert.equal(await page.title(), 'Symblic Beta Gallery');
  assert.match(await page.textContent('h1'), /beta-test record/);
  const rows = await page.locator('table.sb-t tbody tr').count();
  assert.ok(rows >= 25, 'findings, OS receipts and task rows render');
  const canvases = await page.locator('canvas.sb-c').count();
  assert.equal(canvases, 6, 'four grid players and two character players (Matrix rain and twin helix)');
  assert.equal(await page.locator('details.sb-d summary').count() >= 10, true, 'collapsible sources');
});

test('grid players step through saved frames without any API call', async () => {
  const {page, requests} = await boot();
  const first = page.locator('canvas.sb-c:not(.sb-rain)').first();
  const note = page.locator('.sb-frame-note').first();
  await page.getByRole('button', {name: 'Next frame'}).first().click();
  assert.match(await note.textContent(), /Frame 2 of/);
  await page.getByRole('button', {name: 'Previous'}).first().click();
  assert.match(await note.textContent(), /Frame 1 of/);
  await first.getAttribute('aria-label');
  assert.match(await first.getAttribute('aria-label'), /Frame 1: value/);
  // The shared command bar reads the nav registry and the perf beacon posts timings; the gallery itself asks nothing.
  const own = requests.filter(r => r.path.startsWith('/api/') && !/^\/api\/(nav\/pages|perf)/.test(r.path)).map(r => r.path);
  assert.deepEqual(own, [], 'the gallery makes no API requests of its own');
});

test('playback animates the bouncing ball', async () => {
  const {page} = await boot();
  const note = page.locator('.sb-frame-note').first();
  await page.getByRole('button', {name: 'Play', exact: true}).first().click();
  await page.waitForTimeout(1300);
  const text = await note.textContent();
  assert.ok(!/Frame 1 of/.test(text), 'the frame advanced during playback');
  await page.getByRole('button', {name: 'Play', exact: true}).first().click();
});

test('the character animation player draws the recorded frames', async () => {
  const {page} = await boot();
  const rain = page.locator('canvas.sb-rain');
  assert.equal(await rain.count(), 2, 'the Matrix rain player and the twin helix player');
  const label = rain.first().getAttribute('aria-label');
  assert.match(await label, /Character animation frames/);
  await page.locator('canvas.sb-rain').first().scrollIntoViewIfNeeded();
  const pixels = await rain.first().evaluate(cv => {
    const ctx = cv.getContext('2d');
    const d = ctx.getImageData(0, 0, cv.width, cv.height).data;
    let lit = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i + 1] > 40) lit++;
    return lit;
  });
  assert.ok(pixels > 100, 'green cells are drawn (got ' + pixels + ' lit pixels)');
});

test('source documents are available verbatim', async () => {
  const {page} = await boot();
  await page.locator('details.sb-d summary', {hasText: 'The exact English program'}).first().click();
  const body = await page.textContent('details.sb-d[open] .sb-mono');
  assert.match(body, /Remember width is 20\./);
  assert.match(body, /Ask for /);
});

test('phone layout has no horizontal scroll and passes accessibility', async () => {
  const {page} = await boot({mobile: true});
  await noHorizontalScroll(page);
  assert.deepEqual(await axe(page), []);
});
