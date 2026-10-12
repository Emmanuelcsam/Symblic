// Runs the picker's own lexical functions (window.SymblicPicker._lexical) on the cases in argv[2] and prints what
// each edit returned. No browser, network or page: the script is evaluated in a bare context with inert stubs.
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../web/studio/symblic-picker.js', import.meta.url), 'utf8');
const window = {};
const document = { addEventListener() {}, getElementById: () => null, activeElement: null };
vm.runInNewContext(source, { window, document, navigator: {}, Event: class {}, setTimeout, clearTimeout,
  fetch: () => { throw new Error('the probe never fetches'); } });
const lexical = window.SymblicPicker._lexical;
const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = cases.map((c) => {
  const lines = c.source.split('\n');
  const offset = lines.slice(0, c.line || 0).reduce((n, l) => n + l.length + 1, 0) + (c.column || 0);
  const got = c.kind === 'ask' ? lexical.askEdit(c.source, offset, c.addition) : lexical.groupEdit(c.source, c.members);
  return { id: c.id, ok: got.ok, reason: got.reason || null, text: got.text || null, name: got.name || null };
});
process.stdout.write(JSON.stringify(out));
