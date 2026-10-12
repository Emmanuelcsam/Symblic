#!/usr/bin/env node
'use strict';
// Build the static HTML guides in web/studio/symblic-guides/ from an explicit list of documents and examples.
//
//   SYMBLIC_MARKED=/path/to/marked.min.js node tools/scripts/build_symblic_guides.cjs [--source-root ROOT --out DIR]
//
// Needs the Markdown renderer marked 15.0.12 (https://github.com/markedjs/marked, MIT): either `npm install
// marked@15.0.12` next to this repository or SYMBLIC_MARKED pointing at its UMD build. Only the files listed
// below are published; links between them become relative links, links to anything else become plain text that
// names the repository path. Every guide is a self-contained static page (guides.css next to it).
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const DEFAULT_ROOT = path.resolve(__dirname, '../..');   // the repository: this file is tools/scripts/
const DOCS = [
  ['docs/reference/START-HERE.md', 'index.html', 'Start here', 'write'],
  ['docs/reference/EDITOR.md', 'editor.html', 'Underlines and instruction circuits', 'english'],
  ['docs/reference/STEPS.md', 'steps.html', 'Build one step at a time', 'workcards'],
  ['docs/reference/STEPS-EVIDENCE.md', 'steps-evidence.html', 'Small-model results', 'workcards'],
  ['docs/reference/WORKCARDS.md', 'workcards.html', 'Workcards', 'workcards'],
  ['docs/reference/SUPERVISOR.md', 'supervisor.html', 'Supervisor', 'supervisor'],
  ['docs/reference/DISTILLATION.md', 'distillation.html', 'Training a small model', 'write'],
  ['docs/reference/PORTABLE-FINITE.md', 'portable.html', 'Portable execution', 'write'],
  ['docs/reference/VORTICITY-CONSTRUCTION.md', 'vorticity.html', 'Field construction', 'write'],
];
const EXAMPLES = [
  ['examples/steps-parcel-built.sym', 'steps-parcel-built.html', 'Completed parcel program', 'write'],
  ['examples/steps-parcel.json', 'steps-parcel.html', 'Parcel construction request', 'workcards'],
  ['examples/steps-parcel-inputs.json', 'steps-parcel-inputs.html', 'Parcel sample inputs', 'workcards'],
  ['examples/cmatrix.sym', 'cmatrix.html', 'CMatrix example', 'write'],
  ['examples/workcard-team.json', 'team-example.html', 'Team example', 'workcards'],
  ['examples/workcard-slots.json', 'slots-example.html', 'Typed hole example', 'workcards'],
];
const BASE = '';                    // guides link to each other by file name (same folder)
const APP = '../symblic.html';      // the studio page (web/studio/symblic.html; it needs a host, see web/README.md)
const PUBLIC = new Map([...DOCS, ...EXAMPLES].map(([src, name]) => [src, BASE + name]));
const EXTERNAL = new Set([
  "https://github.com/frabjous/logicpenguin/blob/da325893b81f6be1fd20443a9218b556a2e19790/public/js/checkers/derivation-check.js",
  "https://github.com/sylvainhalle/textidote/blob/241beb356ff37dd4495bdaa0d58721888282cd16/Source/Core/src/ca/uqac/lif/textidote/as/AnnotatedString.java",
  "https://github.com/magmide/magmide/blob/79eadf59f4790bd8dbb51d2f41c437c60bcd0873/README.md",
]);
const esc = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function linkTarget(href, source) {
  if (EXTERNAL.has(href)) return href;
  const [relative, fragment] = String(href).split('#');
  const mapped = PUBLIC.get(path.posix.normalize(path.posix.join(path.posix.dirname(source), relative)));
  return mapped ? mapped + (fragment ? '#' + encodeURIComponent(fragment) : '') : null;
}

function renderMarkdown(marked, markdown, source) {
  const renderer = new marked.Renderer();
  renderer.html = token => esc(token.text);
  renderer.image = token => esc(token.text || 'Image');
  renderer.link = function(token) {
    const label = this.parser.parseInline(token.tokens);
    const target = linkTarget(token.href, source);
    return target ? `<a href="${esc(target)}">${label}</a>`
      : `${label} <span class="guide-local">(local repository: <code>${esc(token.href)}</code>)</span>`;
  };
  renderer.code = token => `<pre tabindex="0" aria-label="Code example"><code>${esc(token.text)}</code></pre>\n`;
  renderer.table = function(token) {
    return '<div class="guide-table" tabindex="0" role="region" aria-label="Scrollable table">' + marked.Renderer.prototype.table.call(this, token) + '</div>';
  };
  return marked.parse(markdown, {renderer, gfm:true, breaks:false});
}

function page(title, body, current, tab) {
  const nav = DOCS.map(([, name, label]) => `<a href="${BASE + name}"${name === current ? ' aria-current="page"' : ''}>${esc(label)}</a>`).join('\n');
  const open = tab === 'english' ? 'Open English' : tab === 'workcards' ? 'Open Workcards' : tab === 'supervisor' ? 'Open Supervisor' : 'Open Write';
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f4f1eb"><title>${esc(title)} · Symblic</title>
<link rel="stylesheet" href="${BASE}guides.css"></head><body>
<a class="guide-skip" href="#guide">Skip to guide</a>
<header class="guide-header"><a href="${APP}#write">← Symblic</a><span>Guides</span><a href="${APP}#${tab}">${open}</a></header>
<div class="guide-layout"><details class="guide-menu" open><summary>Browse guides</summary><nav aria-label="Symblic guides">${nav}</nav></details>
<main id="guide" class="guide-prose">${body}<footer><a href="${BASE}index.html">Start here</a> · <a href="${APP}#${tab}">${open}</a><p>Commands and examples run only when you choose to execute them.</p></footer></main></div>
</body></html>\n`;
}

function build(root, output) {
  const marked = require(process.env.SYMBLIC_MARKED || 'marked');
  fs.mkdirSync(output, {recursive:true});
  const sources = [];
  for (const [source, name, title, tab] of DOCS) {
    const bytes = fs.readFileSync(path.join(root, source));
    fs.writeFileSync(path.join(output, name), page(title, renderMarkdown(marked, bytes.toString('utf8'), source), name, tab));
    sources.push({source, sha256:hash(bytes), output:name});
  }
  for (const [source, name, title, tab] of EXAMPLES) {
    const bytes = fs.readFileSync(path.join(root, source));
    const intro = name === 'steps-parcel-built.html'
      ? '<p>This file is the checked output of the documented Llama 1B plus finite-completion trial. It contains no model asks. Run it with <code>tools/symblic run examples/steps-parcel-built.sym</code> and supply the sample parcels, or <a href="../../../examples/steps-parcel-built.sym" download="parcel.sym">download the Symblic file</a>. See <a href="steps-evidence.html">the measured results and limits</a>.</p>'
      : name === 'cmatrix.html'
      ? '<p>This native Symblic program computes bounded character-grid frames without a model: <code>tools/symblic run examples/cmatrix.sym</code>. In the studio page, the saved frame player supplies the animation clock with its Play control.</p>'
      : name === 'steps-parcel-inputs.html'
      ? '<p>For the finished parcel program in the studio page, paste only the inner <code>[...]</code> array into the <strong>parcels</strong> input field. The complete object below is the inputs object for command-line use (<code>--input parcels=...</code>).</p>'
      : '<p>This reviewed request accompanies the Workcards guide. Replace the model and node choices with applicators you have installed before running it.</p>';
    fs.writeFileSync(path.join(output, name), page(title, `<h1>${esc(title)}</h1>${intro}<pre tabindex="0" aria-label="Example source"><code>${esc(bytes.toString('utf8'))}</code></pre>`, name, tab));
    sources.push({source, sha256:hash(bytes), output:name});
  }
  return sources;
}

module.exports = {build, renderMarkdown, linkTarget};
if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length && (args.length !== 4 || args[0] !== '--source-root' || args[2] !== '--out')) throw new Error('Usage: node tools/scripts/build_symblic_guides.cjs [--source-root ROOT --out DIRECTORY]');
  const root = args.length ? path.resolve(args[1]) : DEFAULT_ROOT;
  const output = args.length ? path.resolve(args[3]) : path.join(root, 'web/studio/symblic-guides');
  console.log(JSON.stringify({sources:build(root, output)}, null, 2));
}
