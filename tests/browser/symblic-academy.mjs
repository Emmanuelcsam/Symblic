// The Symblic Academy (web/academy/) served as static files from the repository root: a lesson answered wrong and
// then right, the research map and its reader, reading deep links, the missing-catalog message, the cloze checker,
// and the two buttons that need a host. Ported from the original host's Academy journey; the reader now fetches each
// document as a file ("../.." + its catalog path) where the host's page called a source API.
//
// The journeys need a browser harness (host-harness.mjs) whose root is this repository: they load /web/academy/ from
// it. The host's own harness served the host's checkout, where the page was /symblic-learn.html. Without a harness the
// journeys are reported as skipped. The first test checks, with Node alone, the catalog facts the journeys rely on.
// Synthetic browser state only; the first fetch in the deep-link journey is answered with a 503 on purpose.
import nodeTest, {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {test, available, launch, open, axe, noHorizontalScroll, root} from './host-harness.mjs';

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const PAGE = '/web/academy/index.html';
const CATALOG = '/web/academy/symblic-academy-content.js';
const ROOTS = ['/docs/', '/examples/', '/benchmarks/', '/kits/'];
// Without a harness, or with one that serves another checkout (no Academy at this path), the journeys are skipped.
const served = available && existsSync(path.join(root, PAGE));
const SKIP = available
  ? `the browser harness serves ${root}, which has no ${PAGE}; these journeys need one that serves this repository`
  : 'needs a browser harness that serves this repository (SYMBLIC_BROWSER_HARNESS, see tests/browser/README.md) and '
    + 'Playwright; neither is part of this repository';
const journey = served ? test : (name) => nodeTest(name, {skip: SKIP}, () => {});
const base = served ? root : repository;

const sandbox = {window: {}};
vm.runInNewContext(await fs.readFile(base + CATALOG, 'utf8'), sandbox);
// Copied out of the sandbox so that its arrays and objects compare equal to this realm's.
const data = JSON.parse(JSON.stringify(sandbox.window.SymblicAcademyContent));
const operatorsPath = '/docs/reference/OPERATORS.md';
const checkedMathPath = '/examples/small-model-math-20261007/README.md';
const checkedMath = data.sources.find(source => source.url === checkedMathPath);
const checkedMathBytes = await fs.readFile(base + checkedMathPath);
// The research map's search (renderResearchMap in web/academy/symblic-learn.js).
const search = (query) => data.sources.filter(s => [s.title, ...s.headings, ...s.lessons.map(l => l.title)]
  .join(' ').toLocaleLowerCase().includes(query.toLocaleLowerCase().trim()));
// The link contract: documents under the four roots open in the reader, other repository files open as files
// ("../.." + path from web/academy/), and external links stay as they are.
const href = (url) => ROOTS.some(r => url.startsWith(r)) ? 'index.html?reading=' + encodeURIComponent(url) + '#research'
  : url.startsWith('/') ? '../..' + url.split('/').map(encodeURIComponent).join('/') : url;
const mastery = () => localStorage.setItem('symblic_mastery_v1',
  JSON.stringify({lvl: 0, bite: 0, completed: {'0-0': true}, xp: 10, streak: 1}));
// The stand-in's toast fades out 2.6 s after it appears; axe reads a nearly transparent toast as low contrast, so the
// accessibility checks wait until no toast is on screen.
// A phone browser zooms out to show a page wider than its screen, and window.innerWidth then grows with the page, so
// the page's width is also compared with the viewport the journey asked for.
const fitsScreen = async (page) => await noHorizontalScroll(page)
  && await page.evaluate(width => document.documentElement.scrollWidth <= width + 1, page.viewportSize().width);
const toastGone = (page) => page.waitForFunction(() => {
  const toast = document.getElementById('toast');
  return !toast || (!toast.classList.contains('show') && getComputedStyle(toast).opacity === '0');
});

nodeTest('the catalog facts the journeys rely on', () => {
  assert.ok(checkedMath, 'the checked mathematics README is in the research map');
  assert.equal(checkedMath.sha256, createHash('sha256').update(checkedMathBytes).digest('hex'));
  assert.deepEqual(search(checkedMath.title).map(s => s.url), [checkedMathPath]);
  assert.deepEqual(search('Exact finite operators').map(s => s.url), [operatorsPath]);
  const lesson = data.sources.find(s => s.url === operatorsPath).lessons[0];
  assert.ok(data.levels[lesson.level].bites[lesson.bite].references.some(r => r.url === operatorsPath));
  assert.ok(data.levels[10].bites[0].reflection.model);
});

let browser;
before(async () => { if (served) browser = await launch(); });
after(async () => { await browser?.close(); });

for (const mobile of [false, true]) for (const scheme of ['light', 'dark']) {
  journey(`lesson, research map and reader (${mobile ? 'phone' : 'desktop'}, ${scheme})`, async () => {
    const {context, page, errors, requests} = await open(browser, PAGE + '#mastery', () => undefined, {
      mobile, storage: mastery,
      // The reader shows a document as text: markup in it must not run.
      files: {[operatorsPath]: {body: 'Original source <script>window.__pwned=1</script>', contentType: 'text/markdown'}},
    });
    try {
      await page.emulateMedia({colorScheme: scheme});
      await page.locator('#slBiteCard').waitFor();
      assert.equal(await fitsScreen(page), true);
      // A completed checkpoint can be practised again without earning its XP twice.
      await page.getByRole('button', {name: 'Practise this checkpoint again'}).click();
      await page.locator(`#slCpOpts [data-opt="${data.levels[0].bites[0].ans}"]`).click();
      assert.equal(await page.evaluate(() => JSON.parse(localStorage.symblic_mastery_v1).xp), 10);
      // A new checkpoint: a wrong option shows its own feedback and keeps Next disabled; the right one earns XP once.
      await page.locator('[data-lvl="10"]').click();
      await page.getByRole('heading', {name: 'Worked example', exact: true}).waitFor();
      const b = data.levels[10].bites[0];
      const wrong = b.ans === 0 ? 1 : 0;
      await page.locator(`#slCpOpts [data-opt="${wrong}"]`).click();
      assert.ok((await page.locator('#slCpFeedback').innerText()).includes(b.feedback[wrong]));
      assert.equal(await page.locator('#slBtnNext').isDisabled(), true);
      await page.locator(`#slCpOpts [data-opt="${b.ans}"]`).click();
      await page.locator(`#slCpOpts [data-opt="${b.ans}"]`).click({force: true});
      assert.equal(await page.evaluate(() => JSON.parse(localStorage.symblic_mastery_v1).xp), 20);
      assert.equal(await page.locator('#slBtnNext').isDisabled(), false);
      await page.getByLabel('Your explanation (saved on this browser)')
        .fill('Positive curvature is the assumption; a zero derivative alone is insufficient.');
      await page.getByText('Compare with a worked explanation', {exact: true}).click();
      await page.getByText(b.reflection.model, {exact: true}).waitFor();
      assert.equal(await fitsScreen(page), true);
      await toastGone(page);
      assert.deepEqual(await axe(page), []);
      // The research map: a search, a document shown as plain text, then a lesson that links the document.
      await page.evaluate(() => { location.hash = 'research'; });
      await page.getByLabel('Find a topic, document or section').fill('Exact finite operators');
      assert.equal(await page.locator('.sl-research-record').count(), 1);
      await page.getByText('Read the original here', {exact: true}).click();
      await page.getByText('Original source <script>window.__pwned=1</script>', {exact: true}).waitFor();
      assert.equal(await page.evaluate(() => window.__pwned), undefined);
      await page.locator('.sl-research-record button').first().click();
      await page.locator('#slBiteCard').waitFor();
      // A document read from the repository: the file's own text, and bytes that match the catalog's hash.
      await page.evaluate(() => { location.hash = 'research'; });
      await page.getByLabel('Find a topic, document or section').fill(checkedMath.title);
      assert.equal(await page.locator('.sl-research-record').count(), 1);
      assert.match(await page.locator('#slResearchCount').innerText(), new RegExp(`^1 of ${data.sources.length} sources`));
      assert.equal(await page.locator('.sl-research-record h2 a').getAttribute('href'), href(checkedMathPath));
      await page.getByText('Read the original here', {exact: true}).click();
      await page.waitForFunction(expected => document.querySelector('.sl-research-record pre')?.textContent === expected,
        checkedMathBytes.toString('utf8'));
      assert.equal(await fitsScreen(page), true);
      await toastGone(page);
      assert.deepEqual(await page.evaluate(async () => (await axe.run()).violations
        .map(v => ({id: v.id, targets: v.nodes.map(n => n.target)}))), []);
      assert.doesNotMatch(await page.locator('.sl-research-record > p').first().innerText(), /changed since/);
      const original = page.getByRole('region', {name: `Original source: ${checkedMath.title}`});
      await original.focus();
      await page.keyboard.press('PageDown');
      await page.waitForFunction(() => document.querySelector('.sl-research-record pre').scrollTop > 0);
      await page.keyboard.press('ArrowLeft'); await page.keyboard.press('ArrowRight');
      assert.equal(await page.evaluate(() => location.hash), '#research', 'reading keys do not switch sections');
      if (process.env.AUDIT_OUTPUT) {
        await page.screenshot({path: `${process.env.AUDIT_OUTPUT}/academy-source-${mobile ? 'phone' : 'desktop'}-${scheme}.png`});
      }
      await page.evaluate(() => { location.hash = 'readings'; });
      await page.locator('.sl-reading-body').waitFor();
      assert.equal(await page.locator('.sl-reading-tab-btn').count(), data.levels.length - 7, 'one reading per level after the seventh');
      assert.equal(await fitsScreen(page), true);
      // The practice sections with an input row and with long code lines fit the screen too.
      for (const [section, part] of [['drills', '.sl-drill-input-row'], ['parsons', '.sl-parsons-grid']]) {
        await page.evaluate(id => { location.hash = id; }, section);
        await page.locator(part).first().waitFor();
        assert.equal(await fitsScreen(page), true, `#${section} fits the screen`);
      }
      await page.evaluate(() => { location.hash = 'flashcards'; });
      await page.getByRole('heading', {name: 'Symblic Memory Solidification Deck'}).waitFor();
      assert.deepEqual(errors, []);
      assert.deepEqual(requests, [], 'the static page calls no host API');
    } finally { await context.close(); }
  });
}

journey('a missing catalog fails visibly instead of showing an empty course', async () => {
  const {context, page} = await open(browser, PAGE, () => undefined, {files: {[CATALOG]: {status: 404, body: ''}}});
  try { await page.getByText('The expanded academy content could not load. Reload this page to retry.').waitFor(); }
  finally { await context.close(); }
});

journey('a reading deep link opens the reader and recovers from an unavailable document', async () => {
  const {context, page, requests} = await open(browser, PAGE + '?reading=' + encodeURIComponent(operatorsPath) + '#research',
    () => undefined, {
      files: {[operatorsPath]: {status: 503, body: ''}},
      storage: () => {
        const seen = window.__academyFetches = [];
        const fetch = window.fetch.bind(window);
        window.fetch = (input, init) => { seen.push(String(input)); return fetch(input, init); };
      },
    });
  try {
    await page.getByText('Source unavailable (503). Close and reopen to retry.', {exact: true}).waitFor();
    assert.equal(await page.locator('.sl-research-record').count(), 1);
    await page.route('**' + operatorsPath, route => route.fulfill({body: 'Fresh original text', contentType: 'text/markdown'}));
    const summary = page.getByText('Read the original here', {exact: true});
    await summary.click(); await summary.click();
    await page.getByText('Fresh original text', {exact: true}).waitFor();
    await page.getByText(/This source has changed since the lesson index was built/).waitFor();
    assert.deepEqual(await page.evaluate(() => window.__academyFetches), Array(2).fill('../..' + operatorsPath));
    await page.locator('.sl-research-record button').first().click();
    await page.locator('#slBiteCard').waitFor();
    assert.equal(await page.locator('.sl-lesson-sources a[href*="OPERATORS"]').getAttribute('href'), href(operatorsPath));
    assert.deepEqual(requests, []);
  } finally { await context.close(); }
});

journey('every research map link follows the link contract and names a file of this repository', async () => {
  const {context, page} = await open(browser, PAGE + '#research', () => undefined);
  try {
    await page.locator('.sl-research-record').first().waitFor();
    const links = await page.$$eval('.sl-research-record h2 a', as => as.map(a => a.getAttribute('href')));
    assert.deepEqual(links, data.sources.map(s => href(s.url)));
    for (const link of links) {
      const reading = new URL(link, 'https://academy.invalid/web/academy/').searchParams.get('reading');
      const file = reading ?? new URL(link, 'https://academy.invalid/web/academy/').pathname;
      if (!/^https?:/.test(link)) assert.ok(existsSync(path.join(base, decodeURIComponent(file))), link);
    }
  } finally { await context.close(); }
});

journey('Check and Preview say they need a host and send nothing', async () => {
  const {context, page, requests} = await open(browser, PAGE + '#projects', () => undefined);
  try {
    assert.equal(await page.evaluate(() => Studio.standalone), true, 'the stand-in page library is in use');
    const card = page.locator('.sl-project-card').first();
    const result = card.locator('.sl-project-result');
    for (const name of ['Check with Live Kernel (needs a host)', 'Preview Capsule (needs a host)']) {
      await result.evaluate(el => { el.textContent = ''; });
      await card.getByRole('button', {name}).click();
      assert.match(await result.innerText(), /^Not checked\. Checking and capsule preview call the host API/);
    }
    await page.evaluate(() => { location.hash = 'playground'; });
    for (const name of ['Check Program (needs a host)', 'Preview Capsule (needs a host)']) {
      await page.locator('#slPlayOutput').evaluate(el => { el.textContent = ''; });
      await page.getByRole('button', {name}).click();
      assert.match(await page.locator('#slPlayOutput').innerText(), /tools\/symblic check FILE\.sym/);
    }
    assert.deepEqual(requests, []);
  } finally { await context.close(); }
});

journey('the cloze checker marks each blank right or wrong', async () => {
  const {context, page} = await open(browser, PAGE + '#cloze', () => undefined);
  try {
    const blank = (id) => page.locator(`#blank_cloze-01_${id}`);
    const status = page.locator('#status_cloze-01');
    await page.locator('#btn_check_cloze-01').click();
    assert.equal(await status.innerText(), 'Some tokens are incorrect. Check hints!');
    await blank('b1').fill('let'); await blank('b2').fill('assert'); await blank('b3').fill('1/4');
    await page.locator('#btn_check_cloze-01').click();
    assert.equal(await status.innerText(), 'Some tokens are incorrect. Check hints!');
    assert.deepEqual(await Promise.all(['b1', 'b2', 'b3'].map(id => blank(id).getAttribute('class'))),
      ['sl-blank-input correct', 'sl-blank-input correct', 'sl-blank-input wrong']);
    await blank('b3').fill('3/4');
    await page.locator('#btn_check_cloze-01').click();
    assert.equal(await status.innerText(), '✓ Perfectly correct!');
  } finally { await context.close(); }
});
