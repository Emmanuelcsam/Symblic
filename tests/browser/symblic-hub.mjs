// The Symblic hub (web/hub/index.html, served at /symblic/ by the original host): the tools this repository ships,
// the beta record, demos and records. No API is needed; every link resolves to a file in this repository.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {test, launch, open, axe, noHorizontalScroll, root} from './host-harness.mjs';

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

const boot = async (hash = '', {mobile = false} = {}) =>
  open(browser, '/symblic/' + hash, async () => undefined, {mobile});

test('renders the overview with every tool and the record links', async () => {
  const {page, errors} = await boot();
  assert.equal(await page.title(), 'Symblic');
  const text = await page.textContent('#stage');
  for (const name of ['Command line', 'Language editor', 'Guides']) assert.match(text, new RegExp(name));
  assert.deepEqual(errors, []);
});

test('every page of the hub renders through the menu hashes', async () => {
  const {page, errors} = await boot();
  for (const id of ['lanes', 'demos', 'records', 'agents']) {
    await page.goto('https://dashboard.test/symblic/#' + id);
    await page.waitForFunction((want) => document.body.textContent.includes(want),
      {lanes: 'Which lane', demos: 'fresh agent sessions', records: 'Records', agents: 'bin/skill use-symblic'}[id]);
  }
  assert.deepEqual(errors, []);
});

test('every same-origin link on the hub points at a file the checkout serves', async () => {
  const {page} = await boot();
  const hrefs = new Set();
  for (const id of ['', 'lanes', 'demos', 'records', 'agents']) {
    await page.goto('https://dashboard.test/symblic/#' + id);
    for (const h of await page.$$eval('a[href]', (as) => as.map((a) => a.getAttribute('href')))) hrefs.add(h);
  }
  // The hub links only files of this repository, by relative paths from web/hub/.
  for (const href of hrefs) {
    const clean = href.split('#')[0];
    if (!clean) continue;
    assert.ok(!clean.startsWith('/') && !/^[a-z]+:/i.test(clean), 'unexpected absolute link ' + href);
    await fs.access(path.join(root, 'web', 'hub', clean));
  }
});

test('phone layout has no horizontal scroll and passes accessibility', async () => {
  const {page} = await boot('', {mobile: true});
  await noHorizontalScroll(page);
  assert.deepEqual(await axe(page), []);
});
