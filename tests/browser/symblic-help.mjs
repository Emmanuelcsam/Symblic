// symblic-help journeys: the "?" button, explain mode, topic panel, browse/search and "Load into editor".
// Mocked APIs only (no server, model or store); desktop light and phone dark.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {test, launch, open, axe, noHorizontalScroll} from './host-harness.mjs';

let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });

function fixture(calls) {
  return async (request, url) => {
    const route = url.pathname.replace('/api/automation/symblic/', '');
    calls.push(route);
    if (route === 'meta') return {json: {version: 'fixture', examples: []}};
    if (route === 'check') return {json: {ok: true, plan: [], errors: [], warnings: [], inputs: []}};
    if (route === 'runs') return {json: {runs: []}};
    return undefined;
  };
}

for (const mobile of [false, true]) {
  test(`help: explain, topic, browse, search, load example (${mobile ? 'phone dark' : 'desktop light'})`, async () => {
    const calls = [];
    const {context, page, errors} = await open(browser, '/automation-studio/symblic.html#write', fixture(calls), {mobile});
    try {
      await page.evaluate(theme => Studio.setTheme(theme), mobile ? 'dark' : 'light');
      const fab = page.locator('.sh-fab');
      await fab.waitFor();
      assert.equal(await fab.getAttribute('aria-label'), 'Help: explain a feature');
      await page.locator('#syRun').waitFor();

      // explain mode: clicking Run explains it and does not start a run
      await fab.click();
      await page.locator('.sh-hint').waitFor();
      await page.locator('#syRun').click();
      const panel = page.locator('.sh-panel');
      await panel.waitFor();
      assert.ok((await panel.locator('h2').textContent()).length > 0);
      assert.ok(await panel.locator('h3', {hasText: 'What it is'}).count() >= 1);
      assert.equal(calls.includes('run'), false, 'explain mode must not start a run');
      assert.equal(await page.locator('.sh-hint').count(), 0);
      assert.equal(await noHorizontalScroll(page), true);
      assert.deepEqual(await axe(page), []);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('.sh-panel').count(), 0);

      // browse and search
      await page.keyboard.press('F1');
      await page.locator('.sh-search').waitFor();
      assert.ok(await page.locator('.sh-entry').count() > 20);
      await page.locator('.sh-search').fill('votes');
      assert.ok(await page.locator('.sh-entry').count() >= 1);
      assert.equal(await page.locator('.sh-search').evaluate(el => parseFloat(getComputedStyle(el).fontSize) >= 16), true);
      await page.locator('.sh-entry').first().click();
      await page.locator('.sh-panel h3').first().waitFor();

      // load a Symblic example into the editor
      await page.keyboard.press('Escape');
      await page.keyboard.press('F1');
      await page.locator('.sh-search').fill('spider');
      const entries = page.locator('.sh-entry');
      let loaded = false;
      for (let i = 0; i < Math.min(await entries.count(), 8) && !loaded; i++) {
        await entries.nth(i).click();
        const load = page.locator('.sh-panel button', {hasText: 'Load into editor'});
        if (await load.count()) {
          // Narrative snippets are explanatory; only the explicit checked
          // payload under this disclosure is offered for execution.
          const code = await page.locator('.sh-panel .sh-sources .sh-code').textContent();
          assert.ok(code.length > 0, 'the checked payload is nonempty');
          page.once('dialog', d => d.accept());
          await load.first().click();
          // The loader verifies SHA-256 asynchronously before updating source.
          await page.waitForFunction(expected => document.querySelector('#sySrc')?.value === expected, code);
          const value = await page.locator('#sySrc').inputValue();
          assert.equal(value, code, 'the editor holds the exact checked example');
          loaded = true;
        } else {
          await page.keyboard.press('Escape');
          await page.keyboard.press('F1');
          await page.locator('.sh-search').fill('spider');
        }
      }
      assert.ok(loaded, 'an example with Symblic text can be loaded');
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  });
}
