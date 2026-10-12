// Loads the browser harness the page journeys in this folder were written for, or marks them skipped.
//
// The journeys drive the original host's pages (web/hub, web/studio) in headless Chromium through the host's
// Playwright harness (tests/browser/_mock.mjs in the host checkout): it served the host's files at the host's
// URL paths (/symblic/, /automation-studio/), its shared page library (/studio.js, /studio.css) and answered
// every /api/ call from the test's fixture. That harness, the shared page library and Playwright are not part of
// this repository. When SYMBLIC_BROWSER_HARNESS names a compatible module (or a _mock.mjs sits next to this file)
// the journeys run; otherwise `test` registers each journey as skipped with HOST_ONLY_REASON, so
// `node --test tests/browser/` reports them instead of failing.
import nodeTest from 'node:test';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

export const HOST_ONLY_REASON = "host-only: needs the original host's Playwright page harness (tests/browser/_mock.mjs), "
  + 'its shared page library (/studio.js, /studio.css) and Playwright; none is part of this repository';

const here = path.dirname(fileURLToPath(import.meta.url));
let harness = null;
for (const spec of [process.env.SYMBLIC_BROWSER_HARNESS, path.join(here, '_mock.mjs')].filter(Boolean)) {
  try {
    harness = await import(pathToFileURL(path.resolve(spec)).href);
    break;
  } catch (error) {
    if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  }
}

export const available = harness !== null;
const unavailable = async () => { throw new Error(HOST_ONLY_REASON); };
export const launch = harness?.launch ?? (async () => null);
export const open = harness?.open ?? unavailable;
export const axe = harness?.axe ?? unavailable;
export const noHorizontalScroll = harness?.noHorizontalScroll ?? unavailable;
export const root = harness?.root ?? path.resolve(here, '../..');
export const test = available ? nodeTest : (name) => nodeTest(name, {skip: HOST_ONLY_REASON}, () => {});
