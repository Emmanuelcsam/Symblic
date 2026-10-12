/* English instructions retain their native checked run; model text is rendered only as text. */
(function () {
  'use strict';
  const API = '/api/automation/symblic/', KEY = 'symblic-english-v1';
  const vm = { source: '', by: 'ollama:qwen3:4b-instruct', calls: '32', retries: '2', budget: '12000',
    recovery: null, examples: {}, compiled: null, error: '', busy: false, run: null, id: '', seq: 0, view: null,
    mount: null, poll: null, animation: null, frame: 0, playing: false,
    characterPlayer: null, characterView: null, characterRun: null,
    pixelPlayer: null, pixelView: null, pixelRun: null,
    diagnosticTimer: null, diagnosticSeq: 0, diagnosticReport: null, diagnosticSource: null, diagnosticFailure: '',
    editorDiagnostics: null, circuitCompiled: null, circuitSource: null, picker: null, composer: null,
    execution: 'checked', team: null, teamEnabled: true, teamEditor: null, catalog: null, teamSupported: false,
    catalogMessage: 'Reading available agents…', composerLocked: false };
  try { const s = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    if (s && typeof s.source === 'string') {
      vm.source = s.source.slice(0, 65536);
      for (const k of ['by', 'calls', 'retries', 'budget', 'id']) if (typeof s[k] === 'string') vm[k] = s[k];
      vm.execution = s.execution === 'agent' ? 'agent' : 'checked';
      vm.teamEnabled = typeof s.teamEnabled === 'boolean' ? s.teamEnabled : false;
      if (s.team && typeof s.team === 'object') vm.team = s.team;
      if (s.recovery && /^[0-9a-f]{12}$/.test(s.recovery.from || '') && /^[0-9a-f]{12}$/.test(s.recovery.id || '')) vm.recovery = s.recovery;
    }
  } catch (_) { }
  const linkedRun = new URLSearchParams(location.search).get('english_run');
  if (/^[0-9a-f]{12}$/.test(linkedRun || '')) vm.id = linkedRun;
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'text') node.textContent = v;
      else if (k === 'on') for (const [event, fn] of Object.entries(v)) node.addEventListener(event, fn);
      else if (['value', 'disabled', 'checked', 'hidden', 'open'].includes(k)) node[k] = v;
      else node.setAttribute(k, v);
    }
    for (const c of children.flat()) node.append(typeof c === 'string' ? document.createTextNode(c) : c);
    return node;
  }
  const alive = () => vm.view?.isConnected && vm.view.parentElement === vm.mount;
  function save() {
    const data = Object.fromEntries(['source', 'by', 'calls', 'retries', 'budget', 'id', 'recovery', 'execution', 'team', 'teamEnabled'].map(k => [k, vm[k]]));
    try { sessionStorage.setItem(KEY, JSON.stringify(data)); } catch (_) { }
  }
  function body() {
    const result = { source: vm.source, by: vm.by };
    for (const [key, field, low, high] of [['max_calls', 'calls', 0, 10000], ['retries', 'retries', 0, 5], ['budget', 'budget', 1000, 100000]]) {
      if (!/^\d{1,6}$/.test(vm[field]) || +vm[field] < low || +vm[field] > high)
        throw new Error(`${key} must be a whole number from ${low} to ${high}.`);
      result[key] = +vm[field];
    }
    if (vm.teamEnabled) result.team = selectedTeam('checked');
    return result;
  }
  function selectedTeam(purpose) {
    if (!vm.teamEnabled) return null;
    if (!vm.teamEditor) throw new Error('Team controls are unavailable. Reload before running.');
    if (vm.catalog?.team_capabilities?.version !== 1 || (purpose === 'checked' && !vm.teamSupported))
      throw new Error('This host API does not yet support configured teams here. Reload after its update.');
    return vm.teamEditor.getValue();
  }
  function acceptCatalog(catalog) {
    vm.catalog = catalog; vm.catalogMessage = 'Choose every member explicitly. Refreshing never changes saved choices.';
    vm.teamEditor?.setCatalog(catalog);
    const hint = vm.view?.querySelector('[data-en-catalog-status]'); if (hint) hint.textContent = vm.catalogMessage;
  }
  async function refreshCatalog(force = false) {
    const view = vm.view;
    try {
      const catalog = await Studio.api('/api/symblicos/catalog' + (force ? '?refresh=1' : ''));
      if (vm.view !== view || !alive()) return;
      acceptCatalog(catalog);
      if (force) { vm.catalogMessage = 'Discovery requested. Refresh again after node probes finish; choices stay unchanged.';
        vm.view.querySelector('[data-en-catalog-status]').textContent = vm.catalogMessage; }
    } catch (error) { if (vm.view === view && alive()) { vm.catalogMessage = 'Agent discovery unavailable: ' + error.message;
      vm.view.querySelector('[data-en-catalog-status]').textContent = vm.catalogMessage; } }
  }
  function paintDiagnostics() {
    if (vm.diagnosticReport && vm.diagnosticSource === vm.view?.querySelector('#sy-en-source')?.value)
      vm.editorDiagnostics?.setDiagnostics(vm.diagnosticSource, vm.diagnosticReport.diagnostics || []);
    else vm.editorDiagnostics?.clear(vm.diagnosticFailure || 'Checking source…');
  }
  function selectSourceLine(line) {
    const editor = vm.view?.querySelector('#sy-en-source');
    if (!editor || !Number.isInteger(line) || line < 1) return;
    const lines = editor.value.split('\n');
    if (line > lines.length) return;
    const start = lines.slice(0, line - 1).reduce((count, text) => count + text.length + 1, 0);
    editor.focus({ preventScroll: true }); editor.setSelectionRange(start, start + lines[line - 1].length);
    editor.scrollTop = Math.max(0, (line - 3) * (parseFloat(getComputedStyle(editor).lineHeight) || 26));
    editor.dispatchEvent(new Event('scroll'));
  }
  function paintCircuit() {
    const target = vm.view?.querySelector('[data-en-circuit]');
    if (!target) return;
    const source = vm.view?.querySelector('#sy-en-source')?.value;
    if (vm.circuitCompiled && vm.circuitSource === source && window.SymblicEnglishCircuit) {
      window.SymblicEnglishCircuit.render(target, { compiled: vm.circuitCompiled, source, onSelectLine: selectSourceLine });
    } else target.replaceChildren(el('p', { class: 'hint', text: vm.diagnosticFailure || 'The circuit appears after the source checks pass.' }));
  }
  function scheduleDiagnostics() {
    clearTimeout(vm.diagnosticTimer); vm.diagnosticSeq++;
    if (vm.execution !== 'checked') return;
    vm.diagnosticReport = null; vm.diagnosticSource = null; vm.diagnosticFailure = '';
    vm.circuitCompiled = null; vm.circuitSource = null;
    vm.editorDiagnostics?.clear('Checking source…'); paintCircuit();
    vm.diagnosticTimer = setTimeout(checkDiagnostics, 450);
  }
  async function checkDiagnostics() {
    clearTimeout(vm.diagnosticTimer);
    if (!alive() || vm.execution !== 'checked') return;
    const source = vm.view.querySelector('#sy-en-source')?.value ?? vm.source;
    const draft = vm.source, seq = ++vm.diagnosticSeq;
    try {
      const report = await Studio.api(API + 'editor/check', { source, language: 'english' });
      if (seq !== vm.diagnosticSeq || draft !== vm.source || !alive() || vm.view.querySelector('#sy-en-source')?.value !== source) return;
      if (!report || report.version !== 1 || report.language !== 'english' || (report.source_length_utf16 !== source.length && !(report.source_length_utf16 === null && !report.available && !report.check)))
        throw new Error('The source diagnostic response did not match these instructions.');
      vm.diagnosticReport = report; vm.diagnosticSource = source; vm.diagnosticFailure = '';
      if (report.available && report.ok && report.check?.compiled) {
        vm.circuitCompiled = { ...report.check.compiled, check: report.check.native };
        vm.circuitSource = source;
      } else { vm.circuitCompiled = null; vm.circuitSource = null; }
    } catch (error) {
      if (seq !== vm.diagnosticSeq || draft !== vm.source || !alive()) return;
      vm.diagnosticReport = null; vm.circuitCompiled = null;
      vm.diagnosticFailure = 'Inline checking is unavailable: ' + (error.message || 'try again shortly');
    }
    paintDiagnostics(); paintCircuit();
  }
  function changed() { vm.seq++; vm.compiled = null; vm.error = ''; save();
    const result = vm.view?.querySelector('[data-en-reading]');
    if (result) result.replaceChildren(el('p', { class: 'hint', text: 'Instructions changed. Check them to see their reading.' }));
    scheduleDiagnostics();
  }
  async function request(kind, retainedRun = null) {
    if (vm.busy) return;
    let input; try {
      input = body();
      if (retainedRun) {
        const original = retainedRun.meta?.authoring;
        if (kind !== 'run' || retainedRun.status !== 'failed' || original?.presentation?.kind !== 'binary-pixel-program' ||
            typeof original.document !== 'string' || !/^[0-9a-f]{12}$/.test(retainedRun.id || '')) throw new Error('This saved run cannot be retried here.');
        input.source = original.document; input.keep = retainedRun.id;
        input.by = vm.by || retainedRun.meta?.by || retainedRun.meta?.options?.by;
        if (typeof input.by !== 'string' || !input.by) throw new Error('Choose a worker model before retrying.');
      }
    } catch (e) { vm.error = e.message; paint(); return; }
    const seq = ++vm.seq; vm.busy = true; vm.error = ''; paint();
    try {
      const answer = await Studio.api(API + 'english/' + kind, input);
      if (seq !== vm.seq) return;
      if (kind === 'run') {
        vm.recovery = retainedRun ? { from: retainedRun.id, id: answer.id, kept: Number.isInteger(answer.kept) && answer.kept >= 0 ? answer.kept : null } : null;
        vm.id = answer.id; vm.run = null; vm.frame = 0; save(); await poll(); }
      else vm.compiled = kind === 'preview' ? answer.compiled : answer;
      if (kind === 'preview') vm.compiled = { ...vm.compiled, preview: answer.preview };
    } catch (e) { if (seq === vm.seq) vm.error = e.message || 'The request failed.'; }
    finally { if (seq === vm.seq) { vm.busy = false; paint(); } }
  }
  async function poll() {
    clearTimeout(vm.poll);
    if (!vm.id) return;
    const id = vm.id;
    try { const run = await Studio.api(API + 'run?id=' + encodeURIComponent(id));
      if (id !== vm.id) return;
      const previousFrames = frames().length;
      const wasRunning = ['new', 'starting', 'running'].includes(vm.run?.status);
      vm.run = run;
      const currentFrames = frames().length;
      if (!vm.playing && currentFrames > previousFrames && (wasRunning || ['new', 'starting', 'running'].includes(run.status)))
        vm.frame = currentFrames - 1;
      paintRun();
      if (alive() && ['new', 'starting', 'running'].includes(run.status)) vm.poll = setTimeout(poll, 1500);
    } catch (e) { vm.error = 'Could not read saved progress: ' + e.message; paint(); }
  }
  function frames() {
    return (vm.run?.state?.outputs || []).map(o => o.value).filter(v => v && v.kind === 'grid'
      && ['width', 'height', 'x', 'y'].every(k => Number.isInteger(v[k]))
      && v.width >= 1 && v.width <= 100 && v.height >= 1 && v.height <= 100 && v.width * v.height <= 2500
      && v.x >= 0 && v.x < v.width && v.y >= 0 && v.y < v.height
      && ['string', 'number', 'boolean'].includes(typeof v.value));
  }
  function paintFrame(target) {
    clearTimeout(vm.animation);
    const values = frames(); if (!values.length) { target.replaceChildren(); return; }
    vm.frame %= values.length; const f = values[vm.frame];
    const grid = el('div', { class: 'sy-en-grid', role: 'img', 'aria-label': `Frame ${vm.frame + 1}: ${f.value} at column ${f.x}, row ${f.y}` });
    grid.style.gridTemplateColumns = `repeat(${f.width}, 1fr)`;
    grid.style.setProperty('--sy-grid-ratio', `${f.width} / ${f.height}`);
    for (let row = f.height - 1; row >= 0; row--) for (let col = 0; col < f.width; col++)
      grid.append(el('span', { 'aria-hidden': 'true', class: row === f.y && col === f.x ? '' : 'sy-en-dot', text: row === f.y && col === f.x ? String(f.value).slice(0, 16) : '·' }));
    target.replaceChildren(grid, el('p', { class: 'hint', text: `Saved frame ${vm.frame + 1} of ${values.length}. Row 0 is the bottom. Playback makes no model calls.` }),
      el('div', { class: 'sy-acts' },
        el('button', { class: 'btn', text: vm.playing ? 'Pause' : 'Play frames', on: { click: () => { vm.playing = !vm.playing; paintFrame(target); } } }),
        el('button', { class: 'btn ghost', text: 'Next frame', on: { click: () => { vm.playing = false; vm.frame++; paintFrame(target); } } })));
    if (vm.playing && alive()) vm.animation = setTimeout(() => { if (alive() && target.isConnected) { vm.frame++; paintFrame(target); } }, 650);
  }
  function disposeFrames() {
    clearTimeout(vm.animation); vm.playing = false;
    vm.characterPlayer?.destroy(); vm.characterPlayer = null; vm.characterView = null; vm.characterRun = null;
    vm.pixelPlayer?.destroy(); vm.pixelPlayer = null; vm.pixelView = null; vm.pixelRun = null;
  }
  function paintRun() {
    if (!alive()) return;
    const target = vm.view.querySelector('[data-en-run]'); if (!target) return;
    const run = vm.run; if (!run) { disposeFrames(); target.replaceChildren(); return; }
    const ledger = el('ol', { class: 'sy-en-ledger' });
    for (const row of (run.trace || []).filter(r => r.kind === 'ask' || r.kind === 'ensure').slice(-100))
      ledger.append(el('li', { text: `${row.label || row.kind || 'Statement'} · ${row.status || row.state || ''}${row.note ? ' · ' + row.note : ''}` }));
    const visual = el('div', { 'data-en-frames': '' });
    const state = run.state || {};
    const characterOutputs = Array.isArray(state.outputs) && state.outputs.some(output => output?.value?.kind === 'character-grid');
    if (characterOutputs) vm.characterView ||= el('div', { 'data-en-character-frames': '', 'aria-live': 'off' });
    else { vm.characterPlayer?.destroy(); vm.characterPlayer = null; vm.characterView = null; vm.characterRun = null; }
    const authoring = run.meta?.authoring;
    const retained = authoring?.reuse;
    const validCount = value => Number.isInteger(value) && value >= 0 && value <= 9;
    const recovery = authoring?.presentation?.kind === 'binary-pixel-program' &&
      retained?.scope === 'locally_rechecked_model_work' && /^[0-9a-f]{12}$/.test(retained.from_run || '') &&
      retained.from_run !== vm.id && validCount(retained.kept)
      ? { from: retained.from_run, kept: retained.kept }
      : vm.recovery?.id === vm.id && /^[0-9a-f]{12}$/.test(vm.recovery.from || '') && vm.recovery.from !== vm.id &&
        (vm.recovery.kept === null || validCount(vm.recovery.kept)) ? vm.recovery : null;
    const pixelProgram = run.status === 'done' && authoring?.presentation?.kind === 'binary-pixel-program';
    if (pixelProgram) vm.pixelView ||= el('div', { 'data-en-pixel-program': '', 'aria-live': 'off' });
    else { vm.pixelPlayer?.destroy(); vm.pixelPlayer = null; vm.pixelView = null; vm.pixelRun = null; }
    const errorPosition = Array.isArray(authoring?.source_map)
      ? authoring.source_map.find(row => row.native_line === state.error?.line && row.line) : null;
    vm.pixelPlayer?.hide();
    target.replaceChildren(el('div', { class: 'unit' }, el('h2', { text: 'Saved progress' }),
      el('p', { 'data-en-status': '', text: `${run.status} · ${state.asks || 0} tasks · ${state.calls || 0} model calls · ${state.cached || 0} cached responses` }),
      ...(recovery ? [el('p', { class: 'hint' },
        recovery.kept === null ? 'A new run is retrying the remaining tasks. ' : `${recovery.kept} accepted tasks were locally rechecked for reuse in this new run. `,
        el('a', { href: '?english_run=' + encodeURIComponent(recovery.from) + '#english', text: 'Original failed run' }))] : []),
      ...(state.error ? [el('p', { role: 'alert', text: (errorPosition ? `English line ${errorPosition.line}: ` : '') + (state.error.message || 'The run stopped.') })] : []),
      ...(state.outputs_progress?.partial ? [el('p', { class: 'hint', text: 'Current outputs while this run is in progress.' +
        (state.outputs_progress.omitted ? ` ${state.outputs_progress.omitted} earlier outputs are omitted from this bounded snapshot.` : '') })] : []),
      ...(vm.characterView ? [vm.characterView] : []), ...(vm.pixelView ? [vm.pixelView] : []), visual, ledger,
      ...(run.status === 'failed' && authoring?.presentation?.kind === 'binary-pixel-program' && typeof authoring.document === 'string' ? [
        el('p', { class: 'hint', text: 'Retry uses this saved run’s original instructions and your current worker and task limits. Accepted code is locally rechecked before reuse. Your editor draft and this failed run are preserved.' }),
        el('button', { class: 'btn', 'data-en-retry': '', disabled: vm.busy, text: 'Retry remaining tasks', on: { click: () => request('run', run) } })] : []),
      ...(typeof authoring?.document === 'string' ? [el('details', {}, el('summary', { text: 'Original instructions for this saved run' }), el('pre', { text: authoring.document }))] : []),
      el('details', {}, el('summary', { text: 'All saved outputs' }), el('pre', { text: JSON.stringify(state.outputs || [], null, 2) })),
      el('div', { class: 'sy-acts' },
        el('a', { class: 'btn ghost', href: '?english_run=' + encodeURIComponent(vm.id) + '#english', text: pixelProgram ? 'Link to saved program' : 'Link to saved frames' }),
        el('button', { class: 'btn ghost', text: 'Open full run', on: { click: () => window.SymblicOpenRun?.(vm.id) } }),
        ...(['new', 'starting', 'running'].includes(run.status) ? [el('button', { class: 'btn ghost', text: 'Stop', on: { click: async () => { try { await Studio.api(API + 'stop', { id: vm.id }); await poll(); } catch (e) { vm.error = e.message; paint(); } } } })] : []))));
    paintFrame(visual);
    if (vm.pixelView && (vm.pixelRun !== run || !vm.pixelPlayer)) {
      vm.pixelPlayer?.destroy();
      if (window.SymblicPixelProgram) vm.pixelPlayer = window.SymblicPixelProgram.mount(vm.pixelView, authoring.presentation, state.outputs);
      else vm.pixelView.replaceChildren(el('p', { role: 'status', text: 'The pixel interpreter is unavailable. Reload this page to load it.' }));
      vm.pixelRun = run;
    }
    if (vm.characterView && (vm.characterRun !== run || !vm.characterPlayer)) {
      vm.characterPlayer?.destroy();
      if (window.SymblicFrames) vm.characterPlayer = window.SymblicFrames.mount(vm.characterView, state.outputs);
      else vm.characterView.replaceChildren(el('p', { role: 'status', text: 'Character-grid playback is unavailable. Reload this page to load its player.' }));
      vm.characterRun = run;
    }
  }
  function paint() {
    if (!alive()) return;
    const active = vm.view.contains(document.activeElement) ? document.activeElement : null;
    const focus = active && (active.id || active.getAttribute('aria-label')) ? { id: active.id, label: active.getAttribute('aria-label'), start: active.selectionStart, end: active.selectionEnd,
      direction: active.selectionDirection, scrollTop: active.scrollTop } : null;
    const disclosures = new Set([...vm.view.querySelectorAll('details[data-en-panel][open]')].map(node => node.dataset.enPanel));
    vm.pixelPlayer?.hide();
    vm.editorDiagnostics?.destroy(); vm.editorDiagnostics = null;
    vm.picker?.destroy(); vm.picker = null;
    vm.teamEditor?.destroy(); vm.teamEditor = null;
    vm.composer?.destroy(); vm.composer = null;
    const checked = vm.execution === 'checked';
    const editor = el('textarea', { id: 'sy-en-source', spellcheck: 'false', maxlength: 65536, value: vm.source, disabled: vm.busy,
      on: { input: e => { vm.source = e.target.value; changed(); }, keydown: e => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault();
          if (checked) request(e.shiftKey ? 'preview' : 'run'); else vm.composer?.submit();
        } } } });
    const execution = el('select', { id: 'sy-en-execution', 'aria-label': 'Instruction workflow', disabled: vm.busy,
      on: { change: event => { vm.execution = event.target.value; changed(); paint(); } } },
      el('option', { value: 'checked', text: 'Checked statements' }), el('option', { value: 'agent', text: 'Agent task' }));
    execution.value = vm.execution;
    const example = el('select', { id: 'sy-en-example', disabled: vm.busy, on: { change: e => {
      const row = vm.examples[e.target.value]; if (!row) return;
      vm.source = typeof row === 'string' ? row : row.source; changed(); paint();
    } } }, el('option', { value: '', text: 'Choose an example…' }),
      ...Object.entries(vm.examples).map(([key, row]) => el('option', { value: key, text: row.title || key })));
    const model = el('div', { 'data-en-picker': '' });
    const number = (name, label, low, high) => el('div', {}, el('label', { for: 'sy-en-' + name, text: label }),
      el('input', { id: 'sy-en-' + name, type: 'text', inputmode: 'numeric', value: vm[name], disabled: vm.busy,
        'aria-label': `${label} (${low}–${high})`, on: { input: e => { vm[name] = e.target.value; changed(); } } }));
    const panel = (name, title, ...children) => el('details', { 'data-en-panel': name, open: disclosures.has(name) }, el('summary', { text: title }), ...children);
    const teamTarget = el('div', { 'data-en-team': '' });
    const teamSummary = el('summary');
    const summary = () => { teamSummary.textContent = vm.teamEnabled ? 'Agents · ' + (vm.team?.members?.length || 1) + ((vm.team?.members?.length || 1) === 1 ? ' member' : ' members') : 'Agents · ' + (checked ? 'single statement worker' : 'single agent or native team'); };
    summary();
    const enableTeam = el('input', { type: 'checkbox', id: 'sy-en-team-enabled', checked: vm.teamEnabled, disabled: vm.busy,
      on: { change: event => { vm.teamEnabled = event.target.checked; changed(); summary(); vm.composer?.refreshSelection(); } } });
    const teamPanel = el('details', { 'data-en-panel': 'team', open: disclosures.has('team'), class: 'sy-en-team' }, teamSummary,
      el('label', { class: 'sy-en-check' }, enableTeam, 'Use configured team'),
      el('p', { class: 'hint', text: checked ? 'Each checked Ask starts a fresh typed request for every configured member. Explicit inputs and checks remain in your statements.' : 'Configure the agents for this task. Unsupported combinations are reported before dispatch.' }),
      teamTarget, el('p', { class: 'hint', 'data-en-catalog-status': '', role: 'status', text: vm.catalogMessage }),
      el('button', { type: 'button', class: 'btn ghost', disabled: vm.busy, text: 'Refresh team catalogue', on: { click: () => refreshCatalog(true) } }));
    const reading = el('div', { 'data-en-reading': '' });
    if (checked && vm.compiled) {
      const rows = vm.compiled.statements || [];
      reading.append(el('div', { class: 'unit' }, el('h2', { text: 'How these statements will run' }),
        el('p', { class: 'hint', text: 'Each Ask starts fresh model requests. Only its selected inputs are carried forward. Checks decide whether its result can advance.' }),
        el('ol', { class: 'sy-en-ledger' }, ...rows.map(r => el('li', { text: typeof r === 'string' ? r : r.text || r.instruction || r.kind || JSON.stringify(r) }))),
        el('details', {}, el('summary', { text: 'Inspect compiled program' }), el('pre', { text: vm.compiled.source || '' })),
        ...(vm.compiled.preview ? [el('details', { open: true }, el('summary', { text: 'Exact next model request' }), el('pre', { text: JSON.stringify(vm.compiled.preview.next || vm.compiled.preview, null, 2) }))] : [])));
    }
    const taskTarget = el('div', { 'data-en-task-composer': '' });
    const unit = el('section', { class: 'unit sy-en-compose', 'aria-label': 'English statements' },
      el('div', { class: 'sy-en-heading' }, el('h2', { text: 'English statements' }), execution),
      el('p', { class: 'hint', text: checked ? 'Precise statements, fresh context for each Ask, explicit checks.' : 'Direct instructions for file and tool work. Agents can inspect your selected folder.' }),
      el('label', { for: 'sy-en-source', text: 'Your instructions' }), editor,
      ...(checked ? [el('div', { 'data-en-diagnostics': '' })] : []), teamPanel,
      ...(checked ? [el('div', { class: 'sy-acts sy-en-primary' },
        el('button', { class: 'btn acc', id: 'sy-en-run', disabled: vm.busy, text: vm.busy ? 'Working…' : 'Run statements', on: { click: () => request('run') } }),
        el('button', { class: 'btn', id: 'sy-en-check', disabled: vm.busy, text: 'Check statements', on: { click: () => request('check') } }),
        el('button', { class: 'btn ghost', id: 'sy-en-preview', disabled: vm.busy, text: 'See next task', on: { click: () => request('preview') } })),
        ...(vm.error ? [el('p', { role: 'alert', text: vm.error })] : []),
        reading, el('div', { 'data-en-run': '', 'aria-live': 'polite' }),
        panel('examples', 'Examples and statement guide', el('label', { for: 'sy-en-example', text: 'Start from an example' }), example,
          el('p', { class: 'hint', text: 'Build a character animation starts a construction. Ask the model to make assigns an implementation, Use only selects earlier work, Check tests it, and Display presents it. Remember and Ask for remain available for typed value tasks.' }),
          el('p', { class: 'hint', text: 'Source errors are underlined as you type. Click a problem or press F8. Checking does not run the program.' })),
        panel('limits', 'Statement worker and limits', el('p', { class: 'hint', text: 'The single worker is used only when Use configured team is off. An enabled team overrides it; unavailable team selections refuse rather than fall back.' }),
          model, el('div', { class: 'sy-en-controls' }, number('calls', 'Total model-call budget', 0, 10000), number('retries', 'Corrections per task', 0, 5), number('budget', 'Context characters', 1000, 100000))),
        panel('circuit', 'Your instruction circuit', el('div', { 'data-en-circuit': '' }))] : [taskTarget]));
    vm.view.replaceChildren(unit);
    const circuitPanel = vm.view.querySelector('[data-en-panel="circuit"]'); if (circuitPanel) circuitPanel.setAttribute('data-en-circuit-panel', '');
    if (window.SymblicTeamEditor) vm.teamEditor = window.SymblicTeamEditor.mount(teamTarget, {
      catalog: vm.catalog, team: vm.team, purpose: checked ? 'checked' : 'project', onChange: team => {
        vm.team = team; vm.teamEnabled = true; enableTeam.checked = true; changed(); summary(); vm.composer?.refreshSelection();
      } });
    else teamTarget.append(el('p', { role: 'alert', text: 'Team controls could not load. Reload the page.' }));
    vm.teamEditor?.setDisabled(vm.busy);
    if (checked) {
      if (window.SymblicPicker?.mountChoices) {
        vm.picker = window.SymblicPicker.mountChoices(model, { label: 'Single statement worker', searchLabel: 'Find a statement worker',
          getValue: () => vm.by, disabled: () => vm.busy, emptyLabel: 'Use routing policy',
          onSelect: value => { vm.by = value; changed(); } });
        const select = model.querySelector('select'); if (select) select.id = 'sy-en-by';
      } else model.append(el('input', { id: 'sy-en-by', value: vm.by, disabled: vm.busy, 'aria-label': 'Statement worker',
        on: { input: event => { vm.by = event.target.value; changed(); } } }), el('p', { class: 'hint', text: 'Catalogue unavailable. Your exact saved applicator is retained.' }));
      vm.editorDiagnostics = window.SymblicEditorDiagnostics?.attach(editor, { problems: vm.view.querySelector('[data-en-diagnostics]'), label: 'English statement diagnostics' }) || null;
      paintDiagnostics(); paintCircuit(); paintRun();
    } else if (window.SymblicTaskComposer) {
      vm.composer = window.SymblicTaskComposer.mount(taskTarget, { embedded: true, hideEditor: true,
        getInstruction: () => vm.source, teamEnabled: () => vm.teamEnabled, getTeam: () => selectedTeam('project'), onCatalog: acceptCatalog,
        onLock: locked => { vm.composerLocked = locked; editor.disabled = execution.disabled = enableTeam.disabled = locked; vm.teamEditor?.setDisabled(locked); } });
    } else taskTarget.append(el('p', { role: 'alert', text: 'Agent task controls are unavailable. Reload the page.' }));
    if (focus) {
      const field = focus.id ? vm.view.querySelector('#' + CSS.escape(focus.id)) : [...vm.view.querySelectorAll('[aria-label]')].find(node => node.getAttribute('aria-label') === focus.label);
      if (field && !field.disabled) {
        field.focus({ preventScroll: true });
        if (Number.isInteger(focus.start) && typeof field.setSelectionRange === 'function') field.setSelectionRange(focus.start, focus.end, focus.direction || 'none');
        field.scrollTop = focus.scrollTop;
      }
    }
  }
  function disposeDiagnostics() {
    clearTimeout(vm.poll); disposeFrames();
    clearTimeout(vm.diagnosticTimer); vm.diagnosticSeq++; vm.editorDiagnostics?.destroy(); vm.editorDiagnostics = null;
    vm.picker?.destroy(); vm.picker = null; vm.composer?.destroy(); vm.composer = null; vm.teamEditor?.destroy(); vm.teamEditor = null;
  }
  window.addEventListener('hashchange', () => {
    if (location.hash.split('?')[0] !== '#english') disposeDiagnostics();
  });
  window.SymblicEnglish = { disposeDiagnostics, render(mount) {
    clearTimeout(vm.poll); disposeFrames();
    clearTimeout(vm.diagnosticTimer); vm.diagnosticSeq++; vm.editorDiagnostics?.destroy(); vm.editorDiagnostics = null;
    vm.composer?.destroy(); vm.composer = null;
    vm.mount = mount; vm.view = el('div', { class: 'sy-english' }); mount.replaceChildren(vm.view);
    paint(); scheduleDiagnostics(); if (vm.execution === 'checked') refreshCatalog();
    const view = vm.view;
    Studio.api(API + 'english/examples').then(result => {
      if (vm.view !== view || !alive()) return; vm.examples = result.examples || {}; vm.teamSupported = result.capabilities?.team?.version === 1;
      if (!vm.source && vm.execution === 'checked') { const first = Object.values(vm.examples)[0]; vm.source = typeof first === 'string' ? first : first?.source || ''; save(); }
      if (vm.execution === 'checked') { paint(); scheduleDiagnostics(); }
    }).catch(error => { if (vm.view === view && alive()) { vm.error = error.message; paint(); } });
    if (vm.id) poll();
  } };
})();
