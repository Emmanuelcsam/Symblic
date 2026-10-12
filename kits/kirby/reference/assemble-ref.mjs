// Assembles kirby.html from the reference units exactly the way the compiled build assembles it from accepted
// units: the sheet's Assemble page with every unit's code, in sheet order, joined by a blank line, in place of
// /*UNITS*/. The result is the page the harness must grade N/N.
//
//   node kits/kirby/reference/assemble-ref.mjs OUT.html      (reads ../sheets/kirby.sheet.md)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseSheet, referenceDeclarations, unitSources } from './fill-sheet.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHEET = path.join(HERE, '..', 'sheets', 'kirby.sheet.md');

export function assemble() {
  const text = fs.readFileSync(SHEET, 'utf8');
  const sheet = parseSheet(text);
  const units = unitSources(sheet, referenceDeclarations());
  // the Assemble section's indented block (symblic.spec.sheets._indented): indented lines and blank lines, de-indented
  const lines = sheet.template.lines;
  const block = lines.filter((l) => l.startsWith('    ') || !l.trim()).map((l) => (l.startsWith('    ') ? l.slice(4) : ''));
  while (block.length && !block[0].trim()) block.shift();
  while (block.length && !block[block.length - 1].trim()) block.pop();
  const page = block.join('\n');
  if (!page.includes('/*UNITS*/')) throw new Error('the Assemble section has no /*UNITS*/');
  return page.replace('/*UNITS*/', () => units.join('\n\n'));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const out = process.argv[2];
  if (!out) { console.error('usage: node assemble-ref.mjs OUT.html'); process.exit(2); }
  const html = assemble();
  fs.writeFileSync(out, html);
  console.log(`wrote ${out} (${html.length} characters)`);
}
