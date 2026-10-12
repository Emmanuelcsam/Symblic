/* Atomic: the proof section of the Symblic hub. Reads atomic/results.json (written by the study's
   `study.py export`), renders the two claims with their measured evidence, links the pages tiny models wrote,
   and lets the owner start a build of any sheet on the cluster through the existing spec/run API. */
(function () {
  'use strict';
  const API = '/api/automation/symblic/';
  const MODELS = [
    ['ollama:qwen2.5:0.5b', 'qwen2.5 0.5B (0.4 GB)'], ['ollama:gemma3:1b', 'gemma3 1B (0.8 GB)'], ['ollama:llama3.2:1b', 'llama3.2 1B (1.3 GB)'],
    ['ollama:granite3.3:2b', 'granite3.3 2B (1.5 GB)'], ['ollama:qwen2.5-coder:3b', 'qwen2.5-coder 3B (1.9 GB)'],
    ['ollama:qwen3:4b-instruct', 'qwen3 4B instruct (2.5 GB)'], ['ollama:phi4-mini', 'phi4-mini 3.8B (2.5 GB)'], ['ollama:gemma3:4b', 'gemma3 4B (3.3 GB)'],
  ];
  const SHEETS = [
    ['markdown', 'MiniMark renderer: 13 units, 77 checks'], ['markdown-fine', 'MiniMark as 37 tiny units, 168 checks (one expression each)'], ['markdown-exact', 'MiniMark as 37 tiny units with the exact code given (transcription, the floor)'], ['regex', 'MiniRe regex engine: 17 units, 107 checks'], ['regex-fine', 'MiniRe as 34 tiny units, 172 checks (one expression each)'], ['regex-exact', 'MiniRe as 34 tiny units with the exact code given'],
    ['markdown-mono', 'MiniMark as ONE unit (the control)'], ['regex-mono', 'MiniRe as ONE unit (the control)'],
  ];
  let RESULTS = null, RUN = null, POLL = null, SHEET_TEXT = {}, RUN_NEXT = null;
  // experiment C by hand: a model that fails a sheet is tried on the next, finer one (13 units -> 37 one-expression units -> the same 37 with the code given)
  const LADDER = { markdown: ['markdown', 'markdown-fine', 'markdown-exact'], regex: ['regex', 'regex-fine', 'regex-exact'] };
  const LEVEL = { markdown: 'decomposed', 'markdown-fine': 'fine', 'markdown-exact': 'exact', regex: 'decomposed', 'regex-fine': 'fine', 'regex-exact': 'exact' };

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const unit = (label, hint) => { const u = el('div', 'unit'); u.append(el('span', 'lbl', label)); if (hint) u.append(el('p', 'hint', hint)); return u; };
  const pct = (h) => (h && h.ok && h.cases) ? Math.round(100 * h.pass / h.cases) + '%' : (h && h.error ? 'no file' : '-');

  async function load() {
    if (RESULTS) return RESULTS;
    try { const r = await fetch('atomic/results.json', { cache: 'no-store' }); RESULTS = r.ok ? await r.json() : { rows: [] }; }
    catch (_) { RESULTS = { rows: [] }; }
    return RESULTS;
  }

  function table(head, rows) {
    const wrap = el('div', 'tblwrap'); const t = el('table', 'tbl'); const th = el('thead'); const tr = el('tr');
    for (const h of head) tr.append(el('th', null, h)); th.append(tr); t.append(th);
    const body = el('tbody');
    for (const r of rows) { const row = el('tr'); r.forEach((c, i) => { const td = el('td', (i && !(c instanceof Node)) ? 'num' : null); if (c instanceof Node) td.append(c); else td.textContent = c; row.append(td); }); body.append(row); }
    t.append(body); wrap.append(t); return wrap;
  }

  // cloud baselines appear in the table (the same sheets, run on the host through the owner's CLI) but not in the form
  const LABELS = { 'claude:haiku': 'reference: Claude Haiku (cloud)', 'claude:sonnet': 'reference: Claude Sonnet (cloud)', 'claude:opus': 'reference: Claude Opus (cloud)', 'codex': 'reference: Codex (cloud)' };
  function modelLabel(models) { return (models || []).map((m) => (MODELS.find((x) => x[0] === m) || [m, LABELS[m] || m.replace(/^ollama:/, '')])[1]).join(' + '); }

  function renderResults(m, data) {
    const rows = data.rows || [];
    const byKey = {};
    const variant = (r) => (r.mono ? 'mono' : r.variant && r.variant !== 'units' ? r.variant : r.fine ? 'fine' : 'units');
    for (const r of rows) { byKey[r.target + '|' + (r.models || []).join('+') + '|' + variant(r) + '|' + (r.rep || 1)] = r; }
    const models = Array.from(new Set(rows.map((r) => (r.models || []).join('+'))));
    // local models first, in size order; the cloud reference rows come last (they are the yardstick, not the subject)
    const order = (m) => { const i = MODELS.findIndex((x) => x[0] === m); return i < 0 ? 100 : i; };
    models.sort((a, b) => order(a) - order(b));
    // a build's cell: its score on the unseen cases, then the units the kernel accepted (a stopped build shows how far it got)
    const stoppedAt = (r) => { const u = (r.per_unit || []).find((x) => x.status && x.status !== 'ok'); return u ? 'stopped at ' + String(u.unit || '').replace(/^unit_/, '') : ''; };
    // a build's cell: its score on the unseen cases (only a finished page has one), then the units the kernel accepted
    const cell = (r) => {
      if (!r) return '-';
      const c = el('div');
      const complete = r.units_accepted === r.units_total;
      c.append(el('div', complete ? 'mono' : 'sub', complete ? pct(r.harness) : 'no page'));
      c.append(el('div', 'sub', r.units_accepted + '/' + r.units_total + ' units' + (complete ? '' : ', ' + stoppedAt(r)) + (r.normalized ? ', answers normalized' : '')));
      return c;
    };
    const opener = (r, label) => Object.assign(el('a', 'btn sm ghost', label), { href: r.built_url, target: '_blank', rel: 'noopener' });
    for (const target of ['markdown', 'regex']) {
      const trs = [];
      for (const mk of models) {
        const u = byKey[target + '|' + mk + '|units|1'], f = byKey[target + '|' + mk + '|fine|1'], x = byKey[target + '|' + mk + '|exact|1'], mono = byKey[target + '|' + mk + '|mono|1'];
        if (!u && !mono && !f && !x) continue;
        const links = el('span');
        if (mono && mono.built_url) links.append(opener(mono, 'open one-shot'), document.createTextNode(' '));
        if (u && u.built_url) links.append(opener(u, 'open'));
        if (f && f.built_url) links.append(document.createTextNode(' '), opener(f, 'open fine'));
        if (x && x.built_url) links.append(document.createTextNode(' '), opener(x, 'open exact'));
        if (!links.childNodes.length) links.append(el('span', 'sub', '-'));
        const num = (k) => [u, f, x].filter(Boolean).map((r) => String(r[k])).join(' / ') || '-';
        trs.push([modelLabel(mk.split('+')), mono ? cell(mono) : '-', cell(u), cell(f), cell(x), num('calls'), num('model_minutes'), links]);
      }
      const title = target === 'markdown' ? 'MiniMark renderer (judged on 500 unseen documents against the reference)' : 'MiniRe regex engine (judged on 400 unseen cases against JavaScript\'s own RegExp)';
      const u = unit(title, 'One-shot: the whole specification handed to the model as one unit. Decomposed: ' + (target === 'markdown' ? '13' : '17') + ' units of 2-40 lines, one fresh context each, checked by code before the next. ' + (target === 'markdown' ? 'Fine: the same program as 37 units of one to six lines, each unit an exact expression. Exact: the same 37 units with the function text given, so the model only transcribes (the floor of the ladder). ' : 'The fine and exact sheets exist for MiniMark only. ') + 'Calls and model minutes are listed decomposed / fine / exact.');
      u.append(trs.length ? table(['model', 'one-shot', 'decomposed', 'fine', 'exact', 'calls', 'model min', 'page'], trs) : el('div', 'empty', 'No builds yet.'));
      m.append(u);
    }
    const reps = rows.filter((r) => !r.mono && (r.rep || 1) > 1);
    if (reps.length) {
      const trs = [];
      const groups = {};
      for (const r of rows.filter((x) => !x.mono)) { const k = r.target + (variant(r) !== 'units' ? ' ' + variant(r) : '') + '|' + (r.models || []).join('+'); (groups[k] = groups[k] || []).push(r); }
      for (const [k, list] of Object.entries(groups)) {
        if (list.length < 2) continue;
        const fps = list.map((r) => (r.harness && r.harness.fingerprint) || '-');
        const same = new Set(fps).size === 1 && fps[0] !== '-';
        // unit by unit: how many units came back as the very same text in every build (temperature 0, fixed seed)
        const shas = list.map((r) => Object.fromEntries((r.per_unit || []).filter((x) => x.code_sha).map((x) => [x.unit, x.code_sha])));
        const names = Object.keys(shas[0] || {});
        const identical = names.filter((n) => shas.every((m) => m[n] && m[n] === shas[0][n])).length;
        trs.push([k.replace('|', ': ').replace(/ollama:/g, ''), String(list.length), list.map((r) => pct(r.harness)).join(' / '), same ? 'identical' : 'differs',
          names.length ? identical + ' of ' + names.length : '-', list.map((r) => r.units_accepted + '/' + r.units_total).join(' / ')]);
      }
      const u = unit('Repeatability (claim 1)', 'The same sheet built again from scratch: does the finished program behave identically on the unseen cases? The behaviour fingerprint is a hash of every output on the harness; "same code" counts the units whose accepted text is byte-identical in every build.');
      u.append(table(['sheet: model', 'builds', 'harness', 'behaviour', 'same code', 'units'], trs));
      m.append(u);
    }
    const passing = rows.filter((r) => r.harness && r.harness.ok && r.harness.pass === r.harness.cases);
    const isLocal = (r) => (r.models || []).every((m) => m.startsWith('ollama:'));
    const fpsAll = {};
    for (const r of passing) { (fpsAll[r.target] = fpsAll[r.target] || new Set()).add(r.harness.fingerprint); }
    const u = unit('Across models (experiment A: model-independent correctness)', 'Every build that passes its whole harness behaves identically to every other passing build of the same sheet, whatever model wrote it and at whatever level: one behaviour fingerprint per sheet. The local models are the subject; the cloud builds only show that the yardstick is the same one a proprietary model meets.');
    const lines = Object.entries(fpsAll).map(([t, s]) => { const loc = passing.filter((r) => r.target === t && isLocal(r)), ref = passing.filter((r) => r.target === t && !isLocal(r)); return `${t}: ${loc.length} passing local build${loc.length === 1 ? '' : 's'} (${new Set(loc.map((r) => (r.models || []).join('+'))).size} model${new Set(loc.map((r) => (r.models || []).join('+'))).size === 1 ? '' : 's'}), ${ref.length} cloud reference build${ref.length === 1 ? '' : 's'}, ${s.size} distinct behaviour${s.size === 1 ? '' : 's'} in all`; });
    const kv = el('div', 'sh-kv'); kv.textContent = lines.join('   '); u.append(lines.length ? kv : el('div', 'empty', 'No passing builds yet.'));
    m.append(u);
    if (data.generated) m.append(el('p', 'sh-note', 'Results written ' + data.generated + ' by study.py export; every run folder, call and reply is kept in the study workspace.'));
  }

  async function sheetText(name) {
    if (SHEET_TEXT[name]) return SHEET_TEXT[name];
    const r = await fetch('atomic/sheets/' + name + '.sheet.md', { cache: 'no-store' })   // the study's sheets were not shipped;
    if (!r.ok) throw new Error('The sheet ' + name + ' is not published.');
    return (SHEET_TEXT[name] = await r.text());
  }

  function renderRun(m) {
    const u = unit('Run it yourself', 'Pick a sheet and the local models that may write its units. Each unit runs in a fresh context on a worker node and is checked by code before the next one starts; the finished page opens here.');
    const form = el('div');
    const sheetSel = el('select', 'field'); sheetSel.setAttribute('aria-label', 'Sheet');
    for (const [id, label] of SHEETS) { const o = el('option', null, label); o.value = id; sheetSel.append(o); }
    const own = el('textarea', 'field'); own.rows = 6; own.placeholder = 'Or paste your own spec sheet here (the format is the one these sheets use).'; own.setAttribute('aria-label', 'Your own sheet');
    const boxes = el('div', 'chips');
    for (const [id, label] of MODELS) {
      const lab = el('label', 'chip'); const cb = el('input'); cb.type = 'checkbox'; cb.value = id; cb.checked = id === 'ollama:llama3.2:1b';
      lab.append(cb, document.createTextNode(' ' + label)); boxes.append(lab);
    }
    const num = (label, v, min, max) => { const l = el('label', 'lbl', label); const i = el('input', 'field'); i.type = 'number'; i.value = v; i.min = min; i.max = max; i.style.maxWidth = '120px'; l.append(i); return [l, i]; };
    const [sl, samples] = num('candidates per unit', 2, 1, 8), [rl, retries] = num('repairs per candidate', 3, 0, 5), [ol, rounds] = num('rounds', 2, 1, 6);
    const climbLab = el('label', 'chip'); const climb = el('input'); climb.type = 'checkbox'; climb.checked = true; climbLab.append(climb, document.createTextNode(' climb the ladder: when a sheet fails, try the finer one with the same models'));
    const start = el('button', 'btn acc', 'Start the build'); start.type = 'button';
    const status = el('p', 'hint', '');
    const units = el('div', 'rows');
    const done = el('div', 'sh-actions');
    form.append(el('label', 'lbl', 'sheet'), sheetSel, own, el('span', 'lbl', 'models that may write units'), boxes, el('div', 'sh-actions'), sl, rl, ol, el('div', 'sh-actions'), climbLab, el('div', 'sh-actions'), start, status, units, done);
    u.append(form); m.append(u);
    const launch = async (name, by, note) => {
      const sheet = (name === sheetSel.value && own.value.trim()) || await sheetText(name);
      const res = await Studio.api(API + 'spec/run', { sheet, by, samples: Number(samples.value), retries: Number(retries.value), rounds: Number(rounds.value), title: 'Atomic: ' + name + ' by ' + by.join('+') });
      RUN = { id: res.id, sheet: name, by, climb: climb.checked && !own.value.trim() };
      status.textContent = (note ? note + ' ' : '') + 'Run ' + res.id + ' (' + (LEVEL[name] || name) + ') started. Units appear as the kernel accepts them.';
      poll(status, units, done, start);
    };
    start.onclick = async () => {
      const by = Array.from(boxes.querySelectorAll('input:checked')).map((c) => c.value);
      if (!by.length) { status.textContent = 'Tick at least one model.'; return; }
      start.disabled = true; status.textContent = 'Compiling the sheet and starting the run on the cluster…'; units.replaceChildren(); done.replaceChildren();
      try { await launch(sheetSel.value, by, ''); } catch (e) { status.textContent = e.message; start.disabled = false; }
    };
    RUN_NEXT = (failedAt) => {
      // the next rung for the sheet that just failed, if the ladder has one and the owner asked to climb
      if (!RUN || !RUN.climb) return false;
      const rungs = LADDER[(RUN.sheet || '').split('-')[0]] || [];
      const next = rungs[rungs.indexOf(RUN.sheet) + 1];
      if (!next) return false;
      const note = (LEVEL[RUN.sheet] || RUN.sheet) + ' stopped' + (failedAt ? ' at ' + failedAt : '') + '; trying ' + LEVEL[next] + '.';
      done.append(el('div', 'sub', note));
      launch(next, RUN.by, note).catch((e) => { status.textContent = e.message; start.disabled = false; });
      return true;
    };
  }

  function poll(status, units, done, start) {
    clearInterval(POLL);
    POLL = setInterval(async () => {
      try {
        const v = await Studio.api(API + 'run?id=' + encodeURIComponent(RUN.id));
        const asks = (v.trace || []).filter((r) => r.kind === 'ask');
        const attempts = (v.trace || []).filter((r) => r.kind === 'route-attempt');
        units.replaceChildren();
        for (const a of asks) {
          const row = el('div', 'row'); const dot = el('span', 'dot ' + (a.status === 'ok' ? 'ok' : 'err'));
          const g = el('div', 'grow'); g.append(el('div', 'ttl mono', String(a.name || '').replace(/^unit_/, '')));
          const rej = attempts.filter((t) => String(t.line) === String(a.line) && t.status === 'rejected').length;
          g.append(el('div', 'sub', (a.status === 'ok' ? 'accepted' : a.status) + (rej ? ', ' + rej + ' candidate' + (rej > 1 ? 's' : '') + ' rejected first' : ', first candidate') + (a.note ? ' by ' + a.note : '')));
          row.append(dot, g); units.append(row);
        }
        const running = ['running', 'queued', 'starting', 'resuming'].includes(v.status);
        status.textContent = 'Run ' + RUN.id + ': ' + v.status + ', ' + asks.filter((a) => a.status === 'ok').length + ' unit' + (asks.length === 1 ? '' : 's') + ' accepted, ' + ((v.state || {}).calls || 0) + ' model calls so far.';
        if (!running) {
          clearInterval(POLL); start.disabled = false;
          const out = ((v.state || {}).outputs || []).find((o) => /\.html$/.test(String(o.label || '')));
          if (out && out.value) {
            const blob = new Blob([String(out.value)], { type: 'text/html' }); const url = URL.createObjectURL(blob);
            const a = Object.assign(el('a', 'btn acc', 'open the page the models wrote'), { href: url, target: '_blank', rel: 'noopener' });
            const dl = Object.assign(el('a', 'btn ghost', 'download ' + out.label), { href: url, download: out.label });
            done.append(a, dl);
          } else {
            const failedAt = (asks.find((a) => a.status && a.status !== 'ok') || {}).name;
            if (RUN_NEXT && RUN_NEXT(String(failedAt || '').replace(/^unit_/, ''))) { start.disabled = true; return; }
            done.append(el('span', 'sub', 'The build stopped before the last unit passed; the run is kept under Symblic → Runs.'));
          }
          const link = Object.assign(el('a', 'btn sm ghost', 'inspect the run'), { href: '/automation-studio/symblic.html#runs', target: '_blank', rel: 'noopener' });
          done.append(link);
        }
      } catch (e) { status.textContent = e.message; }
    }, 5000);
  }

  function render(m) {
    m.replaceChildren();
    const c1 = unit('Claim 1: a precise spec makes the result repeatable, whatever the agent (functional determinism)', 'When an objective is written as small, exact steps with checks, different models and different runs arrive at the same behaviour on inputs none of them saw: the checks fix the result, the model only supplies a candidate. The claim is about behaviour, not bytes. Whether two runs also return the same text is measured separately below and is not required.');
    const c2 = unit('Claim 2: small local models compose intricate programs when each unit fits them (capability amplification)', 'A 0.5B-4B model on a CPU-only worker node cannot write a regex engine or a Markdown renderer in one shot. Cut into units that fit it, with examples, one fresh context per unit, several candidates, code-checked repair and only passing code kept, the same fixed models build the whole program. The proof is the finished page and its score on inputs the units never saw. The level of decomposition a model needs is the measurement: it says how much of the intelligence the sheet, the kernel and the checks carried.');
    m.append(c1, c2);
    const how = unit('How it is measured', '');
    const ol = el('ol', 'sh-note');
    for (const t of ['A spec sheet names the file, the shared conventions and the units: contract, numbered steps, exact literals, examples generated from a reference implementation that itself agrees with marked (Markdown) or with JavaScript\'s RegExp (regex).',
      'symblic.spec compiles the sheet into a Symblic program; no model writes the program. tools/symblic runs it: every unit is a fresh model call on a worker node through the host fleet layer, checked in the sandboxed JavaScript kernel, repaired with its failing examples, and only passing code reaches the file.',
      'The control is the same specification as one unit (the one-shot column).',
      'Granularity is the variable: one-shot (whole program), decomposed (13 or 17 units of 2-40 lines with the full conventions in every prompt), fine (37 units of one to six lines, each an exact expression, with a 350-character preamble) and exact (the same 37 units with the function text given). A model that fails at one level is retried at the next: the atom and the prompt must both fit the worker, and the level a model needs says how much of the intelligence the sheet had to carry.',
      'The finished page is judged by an independent harness on hundreds of random inputs the sheet never showed, and its behaviour is fingerprinted so builds can be compared across models and runs.',
      'Three experiments: A, model-independent correctness (the same sheet through different models: one behaviour); B, intelligence versus decomposition (one-shot against decomposed for the same model); C, the minimum capable worker (the same program at coarser and finer granularity until a model completes it).',
      'Answers normalized: where a row says so, the kernel repaired mechanical faults in a worker\'s answer by code before testing (the fenced block that declares the unit, a dropped `function` keyword, the worker\'s own copies of helpers earlier units already passed, a unit declared twice, a bare `name = ...` assignment that the sandbox would ignore but a page would run). Nothing is repaired by a model; the normalized text is what was tested and what shipped.']) ol.append(el('li', null, t));
    how.append(ol); m.append(how);
    const results = el('div'); m.append(results);
    load().then((data) => renderResults(results, data));
    renderRun(m);
  }

  window.SymblicAtomic = { render, stop: () => clearInterval(POLL) };
})();
