/* Symblic — write, check, preview, run and compare formal statement programs (web/studio/symblic.html; needs a host).
   The language and every decision live server-side (symblic/kernel/language.py and symblic/kernel/run.py, through the host's /api/automation/symblic/);
   this page edits, shows and asks. Model text is untrusted: it only ever reaches the page through esc()/att(). */
(function () {
  'use strict';
  const { $, esc, att, toast, api } = Studio;
  const API = '/api/automation/symblic/';
  const DRAFT_KEY = 'symblic-v2-draft';
  const BY_KEY = 'symblic-v2-by';
  const TASK_KEY = 'symblic-v3-task';
  const MODEL_PINS_KEY = 'symblic-v3-model-pins';
  const CTOR_KEY = 'symblic-v4-constructor';
  const KEYWORDS = new Set(['program', 'note', 'section', 'module', 'use', 'given', 'let', 'define', 'fact', 'rule', 'ask',
    'ensure', 'assert', 'expect', 'if', 'elif', 'else', 'end', 'for', 'show', 'return', 'draw', 'group', 'forget', 'pin',
    'delegate', 'observe', 'act', 'workflow', 'term', 'function', 'routine', 'import', 'test']);
  const WORDS = new Set(['with', 'from', 'by', 'each', 'else', 'elif', 'end', 'in', 'then', 'do', 'and', 'or', 'not', 'xor', 'implies', 'iff',
    'all', 'any', 'none', 'every', 'some', 'query', 'holds', 'true', 'false', 'one', 'of', 'as', 'because', 'retry',
    'fail', 'warn', 'to', 'up', 'words', 'length', 'places', 'is', 'mod', 'union', 'intersect', 'minus', 'subset']);
  const TYPES = new Set(['Int', 'Integer', 'Number', 'Bool', 'Boolean', 'Text', 'List', 'Set', 'Record', 'Svg', 'Any']);
  const APPS = [
    ['claude:haiku', 'Claude Haiku'], ['claude:sonnet', 'Claude Sonnet'], ['claude:opus', 'Claude Opus'],
    ['codex', 'Codex'], ['agy', 'Antigravity'], ['ollama:qwen3:4b-instruct', 'Qwen3 4B · worker nodes'],
    ['ollama:llama3.2:1b', 'Llama 3.2 1B · worker nodes'], ['ollama:gemma3:4b', 'Gemma3 4B · worker nodes'],
    ['ollama:phi4-mini', 'Phi-4 mini · worker nodes'], ['ollama:granite3.3:2b', 'Granite 3.3 2B · worker nodes'],
    ['gemini:flash', 'Gemini Flash · browser'], ['chatgpt', 'ChatGPT · browser'],
    ['council:panel', 'Council: panel'], ['council:debate', 'Council: debate'],
  ];
  const STARTER = `program Hello, Symblic.
use profile=verified.
note Models can construct answers, proofs and programs. Checks establish their encoded properties under declared assumptions.

let a = 4 + 4.
assert a = 8.

ask legs: Int in 0..20 "How many legs does a spider have?" with effort=low
ensure legs = a else retry because "a spider has eight legs".

show [a, legs].
`;

  let SRC = STARTER, CHECK = null, META = null, RUNS = null, OPEN = null, OPEN_ID = '', CMPS = null, CMP = null,
    CMP_ID = '', PREVIEW = null, PROGRAMS = null, EVID = null, INPUTS = {}, BY = 'claude:haiku', BUSY = false,
    SIDE = false, LIB = null, LIBTESTS = {}, LOCKS = {}, PAPERMAP = {}, PAPERVIEW = {}, LJOBS = null, LJOB = {}, TJOBS = null, TJOB = null,
    TJOB_ID = '';
  let TASK_OPTIONS = {}, TASK_SOURCE = '';
  let STRICT_MODEL_PINS = false;
  let CTOR = { on: false, mode: 'linear', calls: '0' };   // checked construction, off by default (docs/symblic/CONSTRUCTORS.md)
  let checkTimer = null, pollTimer = null, checkSeq = 0;
  let writeSettingsOpen = false;
  let writeDiagnostics = null, diagnosticReport = null, checkedSource = null, diagnosticSource = null;
  const linkedRun = new URLSearchParams(location.search).get('run') || '';
  if (/^[0-9a-f]{12}$/.test(linkedRun)) OPEN_ID = linkedRun;
  // Build: a spec sheet (docs/symblic/SPEC-SHEETS.md) compiled server-side, units written by local models
  const SHEET_KEY = 'symblic-v2-sheet';
  const BUILD_DEFAULT = ['ollama:qwen3:4b-instruct', 'ollama:phi4-mini', 'ollama:gemma3:4b'];
  let SHEET = '', SHEET_INFO = null, BUILD_BY = BUILD_DEFAULT.slice(), BUILD_OPTS = { samples: 5, retries: 3, rounds: 3 };
  let BUILD_KEEP = '';                 // a spec build whose accepted units a rebuild keeps (docs/symblic/SPEC-SHEETS.md)
  let BUILD_MODE = 'legacy', BUILD_BUDGET = 24000, BUILD_MANIFEST = null;
  let BUILD_PRESENTATION = 'compact', BUILD_DECLARATIONS = '';
  let BUILD_CANDIDATES = '', BUILD_PROBES = '', BUILD_EXTERNALS = '[]', BUILD_COMPARISON = null, BUILD_COMPARING = false;
  try { SRC = localStorage.getItem(DRAFT_KEY) || STARTER; BY = localStorage.getItem(BY_KEY) || BY; } catch (_) { }
  try { SHEET = localStorage.getItem(SHEET_KEY) || ''; } catch (_) { }
  try { STRICT_MODEL_PINS = sessionStorage.getItem(MODEL_PINS_KEY) === 'strict'; } catch (_) { }
  try {
    const saved = JSON.parse(sessionStorage.getItem(CTOR_KEY) || 'null');
    if (saved && typeof saved === 'object') CTOR = { on: saved.on === true, mode: saved.mode === 'linear_diagnose' ? 'linear_diagnose' : 'linear',
      calls: typeof saved.calls === 'string' ? saved.calls.slice(0, 12) : '0' };
  } catch (_) { }
  try {
    const saved = JSON.parse(sessionStorage.getItem(TASK_KEY) || 'null');
    if (saved && saved.source === SRC && saved.inputs && typeof saved.inputs === 'object') {
      TASK_SOURCE = saved.source; TASK_OPTIONS = saved.options || {}; INPUTS = saved.inputs;
      if (TASK_OPTIONS.model_pins === 'strict') STRICT_MODEL_PINS = true;
    }
  } catch (_) { }


  // ---------------------------------------------------------------- helpers
  const hue = (h) => (parseInt(String(h || '0').slice(0, 4), 16) || 0) % 360;
  const swatch = (h) => h ? `<span class="sy-hash" title="${att('fingerprint ' + h)}"><i style="background:hsl(${hue(h)} 62% 52%)"></i>${esc(String(h).slice(0, 8))}</span>` : '';
  const pill = (cls, text) => `<span class="sy-pill ${att(cls || '')}">${esc(text)}</span>`;
  const assuranceLabel = (value) => ({ typed_answer: 'Answer fits the declared type',
    unique_in_declared_domain: 'Unique answer under the written constraints',
    derived_from_inputs: 'Computed from recorded inputs', unattested: 'No independent verification' }[value] || 'Evidence recorded');
  const hasMeasuredAgreement = (a) => !!a && a.route !== 'escalate' && (a.items && a.items.length
    ? a.items.every(hasMeasuredAgreement)
    : (a.samples || []).filter((s) => s.ok && (s.round || 1) === (a.rounds || 1)).length >= 2);
  const when = (t) => t ? new Date(t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
  const busy = '<div class="unit"><div class="empty"><span class="busy"><i></i><i></i><i></i></span></div></div>';
  const running = (st) => ['running', 'starting', 'new'].includes(st);
  function saveDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, SRC);
      if (SRC === TASK_SOURCE) sessionStorage.setItem(TASK_KEY, JSON.stringify({ source: SRC, inputs: INPUTS, options: TASK_OPTIONS }));
      else sessionStorage.removeItem(TASK_KEY);
    } catch (_) { }
  }
  const strictModelPinsAvailable = () => META?.features?.strict_model_pins === true;
  function setStrictModelPins(value) {
    STRICT_MODEL_PINS = value === true;
    TASK_OPTIONS = { ...TASK_OPTIONS };
    delete TASK_OPTIONS.model_pins;
    if (STRICT_MODEL_PINS) TASK_OPTIONS.model_pins = 'strict';
    try { sessionStorage.setItem(MODEL_PINS_KEY, STRICT_MODEL_PINS ? 'strict' : ''); } catch (_) { }
    saveDraft();
  }
  // Checked construction is offered only when meta reports the API marker (an old route would drop the policy), only
  // for a native program, and never over a bound task policy (Logic task, delegated contract, reopened run): those
  // options go out exactly as bound. Enabled, the run sends the exact API contract: constructor, determine=false,
  // solve off and max_calls (the model fallback budget; 0 = none).
  const CTOR_MODES = ['linear', 'linear_diagnose'];
  const constructorAvailable = () => {
    const f = META?.features?.constructor_options;
    return !!f && f.version === 1 && Array.isArray(f.modes) && CTOR_MODES.every((m) => f.modes.includes(m));
  };
  const boundTask = () => SRC === TASK_SOURCE && Object.keys(TASK_OPTIONS).some((k) => k !== 'model_pins');
  const ctorBlock = () => (isPaper(SRC) ? 'paper' : boundTask() ? 'bound' : !constructorAvailable() ? 'unavailable' : '');
  const CTOR_REASONS = {
    unavailable: 'This server does not report checked-construction support. A selected setting blocks Run until the server supports it or you clear it.',
    paper: 'These controls apply to native programs. A paper runs on its ordinary path until paper forwarding is verified.',
    bound: 'This task carries its own run policy, including any checked-construction setting, so Run uses it exactly as prepared.' };
  const ctorCalls = () => (/^\d{1,5}$/.test(CTOR.calls) && +CTOR.calls <= 10000 ? +CTOR.calls : null);
  function saveCtor() { try { sessionStorage.setItem(CTOR_KEY, JSON.stringify(CTOR)); } catch (_) { } }

  // A paper (.symd: Markdown with ```symblic blocks, docs/symblic/LANGUAGE-3.md) is told apart by its fences or
  // front matter; a program never contains ``` and never starts with ---.
  const isPaper = (text) => /^\s*(```|~~~)\s*(symblic|sym)\s*$/m.test(text) || /^---\s*$/m.test(String(text).split('\n')[0] || '');
  window.SymblicFormat = (text) => (isPaper(text) ? 'paper' : 'program');   // the agent picker edits only a program

  // ---------------------------------------------------------------- highlighting
  function highlight(text) {
    const out = [];
    let inTriple = null;
    for (const line of text.split('\n')) {
      out.push(hlLine(line, inTriple, (st) => { inTriple = st; }));
    }
    return out.join('\n') + '\n';
  }
  function hlLine(line, triple, setTriple) {
    let i = 0, html = '';
    const n = line.length;
    if (triple) {
      const end = line.indexOf(triple);
      if (end < 0) return `<span class="k-str">${esc(line)}</span>`;
      html += `<span class="k-str">${esc(line.slice(0, end + 3))}</span>`;
      i = end + 3;
      setTriple(null);
    } else {
      const first = (line.trim().match(/^[A-Za-z_]+/) || [''])[0].toLowerCase();
      if (['program', 'note', 'section', 'module', 'workflow'].includes(first)) {
        const at = line.toLowerCase().indexOf(first);
        return esc(line.slice(0, at)) + `<span class="k-kw">${esc(line.slice(at, at + first.length))}</span>` +
          `<span class="k-prose">${esc(line.slice(at + first.length))}</span>`;
      }
      const formal = KEYWORDS.has(first) || /^\s*[\d(\[{"'¬∀∃#-]/.test(line) || /^\s*(with|from|by|for each)\b/i.test(line) || !line.trim();
      if (!formal) return `<span class="k-prose">${esc(line)}</span>`;
    }
    let atStart = !triple;
    while (i < n) {
      const ch = line[i];
      if (ch === '#') { html += `<span class="k-com">${esc(line.slice(i))}</span>`; break; }
      if (ch === '"' || ch === "'") {
        const q3 = line.startsWith(ch.repeat(3), i);
        if (q3) {
          const end = line.indexOf(ch.repeat(3), i + 3);
          if (end < 0) { html += `<span class="k-str">${esc(line.slice(i))}</span>`; setTriple(ch.repeat(3)); break; }
          html += `<span class="k-str">${esc(line.slice(i, end + 3))}</span>`; i = end + 3; continue;
        }
        if (ch === "'" && i > 0 && /\w/.test(line[i - 1])) { html += esc(ch); i++; continue; }
        let j = i + 1;
        while (j < n && line[j] !== ch) { if (line[j] === '\\') j++; j++; }
        html += `<span class="k-str">${esc(line.slice(i, j + 1))}</span>`; i = j + 1; continue;
      }
      const num = /^\d+(\.\d+)?/.exec(line.slice(i));
      if (num && !(i > 0 && /\w/.test(line[i - 1]))) { html += `<span class="k-num">${esc(num[0])}</span>`; i += num[0].length; continue; }
      const word = /^[A-Za-z_]\w*/.exec(line.slice(i));
      if (word) {
        const w = word[0], lw = w.toLowerCase();
        if ((atStart && KEYWORDS.has(lw)) || WORDS.has(lw)) html += `<span class="k-kw">${esc(w)}</span>`;
        else if (TYPES.has(w)) html += `<span class="k-ty">${esc(w)}</span>`;
        else if (/^[A-Z]$|^[A-Z][a-z]*$/.test(w) && /\brule\b|\bquery\b|\bholds\b/.test(line)) html += `<span class="k-var">${esc(w)}</span>`;
        else html += esc(w);
        i += w.length; atStart = false; continue;
      }
      if (/[=<>!∧∨¬→↔∈∉∪∩⊆∀∃≠≤≥+\-*/^%]/.test(ch)) { html += `<span class="k-op">${esc(ch)}</span>`; i++; continue; }
      if (ch !== ' ' && ch !== '\t') atStart = false;
      html += esc(ch); i++;
    }
    return html;
  }

  // ---------------------------------------------------------------- data
  async function loadMeta() { try { META = await api(API + 'meta'); } catch (e) { META = { error: e.message }; } }
  async function loadRuns() { try { RUNS = (await api(API + 'runs')).runs; } catch (e) { RUNS = RUNS || []; toast(e.message); } }
  async function loadRun(id) { try { OPEN = await api(API + 'run?id=' + encodeURIComponent(id)); OPEN_ID = id; } catch (e) { toast(e.message); } }
  async function loadCmps() { try { CMPS = (await api(API + 'compares')).compares; } catch (e) { CMPS = CMPS || []; } }
  async function loadCmp(id) { try { CMP = await api(API + 'compare?id=' + encodeURIComponent(id)); CMP_ID = id; } catch (e) { toast(e.message); } }
  async function loadPrograms() { try { PROGRAMS = (await api(API + 'programs')).programs; } catch (e) { PROGRAMS = []; } }
  async function loadLibrary() { try { LIB = (await api(API + 'library')).modules; } catch (e) { LIB = { error: e.message }; } }
  async function loadPaperMap(id) {
    if (id in PAPERMAP) return;
    try { PAPERMAP[id] = await api(API + 'paper/map?run=' + encodeURIComponent(id)); } catch (_) { PAPERMAP[id] = null; }
  }
  async function loadPaperView(id) {
    try { PAPERVIEW[id] = await api(API + 'paper/view?id=' + encodeURIComponent(id)); } catch (_) { PAPERVIEW[id] = null; }
  }
  async function loadTightens() { try { TJOBS = (await api(API + 'tightens')).tightens; } catch (e) { TJOBS = TJOBS || []; } }
  async function loadTighten(id) { try { TJOB = await api(API + 'tighten?id=' + encodeURIComponent(id)); TJOB_ID = id; } catch (e) { toast(e.message); } }
  async function loadEvidence() { try { EVID = await api(API + 'evidence'); } catch (e) { EVID = { error: e.message }; } }

  function invalidateCheck() {
    clearTimeout(checkTimer);
    checkSeq++;
    CHECK = null; checkedSource = null; diagnosticReport = null; diagnosticSource = null;
    writeDiagnostics?.clear('Checking source…');
    $('syGut')?.querySelectorAll('b').forEach(b => b.classList.remove('err', 'warn'));
    const status = $('syDiag');
    if (status) status.textContent = 'Checking source…';
  }
  function scheduleCheck() {
    invalidateCheck();
    checkTimer = setTimeout(runCheck, 450);
  }
  async function runCheck() {
    invalidateCheck();
    const seq = checkSeq, draft = SRC, source = $('sySrc')?.value ?? SRC, language = isPaper(source) ? 'paper' : 'native';
    try {
      let res, report = null;
      try {
        report = await api(API + 'editor/check', { source, language });
        if (!report || report.version !== 1 || report.language !== language || (report.source_length_utf16 !== source.length && !(report.source_length_utf16 === null && !report.available && !report.check)))
          throw new Error('The source diagnostic response did not match this editor.');
        res = report.check;
        if (!report.available || !res) res = { ok: false, errors: [], warnings: [], plan: [] };
      } catch (error) {
        if (error.status !== 404 && error.status !== 503) throw error;
        res = await api(API + (language === 'paper' ? 'paper/check' : 'check'), { source });
      }
      if (seq !== checkSeq || draft !== SRC || ($('sySrc') && $('sySrc').value !== source)) return;
      if (language === 'paper') res.name = res.title || res.name;
      CHECK = res; checkedSource = draft; diagnosticReport = report; diagnosticSource = source;
    } catch (e) {
      if (seq !== checkSeq || draft !== SRC || ($('sySrc') && $('sySrc').value !== source)) return;
      CHECK = { ok: false, errors: [{ line: 0, message: e.message }], warnings: [], plan: [] };
      checkedSource = draft; diagnosticReport = null; diagnosticSource = source;
    }
    paintDiag();
    paintInputs();
    const nm = $('syName');
    if (nm) nm.textContent = CHECK && CHECK.name ? CHECK.name : '';
    const pm = $('syMode');
    if (pm) pm.hidden = !isPaper(SRC);
    paintTestsButton();
  }

  function paintTestsButton() {
    const b = $('syTests');
    if (b) b.hidden = isPaper(SRC) || !((CHECK && CHECK.plan) || []).some((r) => r.kind === 'test');
    const c = $('syCryst');
    if (c) c.hidden = isPaper(SRC) || !routinesInPlan().length;
  }

  function routinesInPlan() {
    return ((CHECK && CHECK.plan) || []).filter((r) => r.kind === 'routine' && !r.depth)
      .map((r) => (/^routine (\w+)\(/.exec(r.label) || [])[1]).filter(Boolean);
  }

  // A sheet with agent checkboxes (and optional extra fields), like Compare's.
  function agentSheet(title, hint, defaults, extra, onGo) {
    const veil = document.createElement('div');
    veil.className = 'veil on';
    const sheet = document.createElement('div');
    sheet.className = 'sheet on';
    sheet.setAttribute('role', 'dialog');
    sheet.innerHTML = `<span class="lbl">${esc(title)}</span><p class="hint">${esc(hint)}</p>${extra || ''}
      ${defaults ? `<div class="sy-sheet-apps">${APPS.filter(([v]) => !v.startsWith('council')).map(([v, t]) => `<label><input type="checkbox" data-agent value="${att(v)}" ${defaults.includes(v) ? 'checked' : ''}> ${esc(t)}</label>`).join('')}</div>` : ''}
      <div class="sy-acts"><button class="btn acc" data-go>Start</button><button class="btn ghost" data-x>Cancel</button></div>`;
    document.body.append(veil, sheet);
    const close = () => { veil.remove(); sheet.remove(); };
    veil.onclick = close;
    sheet.querySelector('[data-x]').onclick = close;
    sheet.querySelector('[data-go]').onclick = async () => {
      const agents = [...sheet.querySelectorAll('[data-agent]:checked')].map((c) => c.value);
      try { if (await onGo(sheet, agents) !== false) close(); } catch (e) { toast(e.message); }
    };
  }

  function openCrystalSheet() {
    if (CHECK && !CHECK.ok) { toast('Fix the errors first'); return; }
    const names = routinesInPlan();
    agentSheet('Crystallise a routine',
      `The routine is asked once per input below, by ${BY} with its own votes. Agreed answers become a fixed lookup table. This makes them repeatable; factual validation still needs a separate reference or check. Inputs outside the table are refused.`,
      null,
      `<div class="fieldrow"><label class="hint" for="syCrR">Routine</label><select class="field" id="syCrR">${names.map((n) => `<option value="${att(n)}">${esc(n)}</option>`).join('')}</select></div>
       <label class="hint" for="syCrIn" style="display:block;margin-top:8px">Inputs, one per line (text, a number, or a JSON list of arguments)</label>
       <textarea class="field" id="syCrIn" rows="6" spellcheck="false"></textarea>
       <div class="fieldrow" style="margin-top:8px"><label class="hint" for="syCrA">Keep answers agreed by</label><select class="field" id="syCrA"><option value="1">every vote</option><option value="0.8">80% of votes</option></select></div>`,
      async (sheet) => {
        const lines = sheet.querySelector('#syCrIn').value.split('\n').map((l) => l.trim()).filter(Boolean);
        if (!lines.length) { toast('Give at least one input'); return false; }
        const domain = lines.map((l) => { try { return /^[\[{"\d-]|^(true|false)$/.test(l) ? JSON.parse(l) : l; } catch (_) { return l; } });
        await api(API + 'lang/crystallise', { source: SRC, routine: sheet.querySelector('#syCrR').value, domain, by: BY,
          min_agreement: +sheet.querySelector('#syCrA').value });
        toast('Crystallising: see Language → Jobs');
        LJOBS = null;
        Studio.go('language');
      });
  }

  let exampleDownloadsOpen = false, exampleDownloads = null, exampleDownloadsRequest = null;
  function exampleDownloadUrl(id, name) {
    return API + 'examples/artifact?' + new URLSearchParams({ id, name });
  }
  function checkedDownloadBundles(data) {
    if (!data || !Array.isArray(data.bundles) || data.bundles.length > 32) throw new Error('The checked download list could not be read.');
    for (const bundle of data.bundles) {
      if (!bundle || typeof bundle.id !== 'string' || !/^[a-zA-Z0-9_-]{1,100}$/.test(bundle.id)
          || typeof bundle.title !== 'string' || !Array.isArray(bundle.files) || bundle.files.length > 200)
        throw new Error('The checked download list could not be read.');
      for (const file of bundle.files) {
        if (!file || typeof file.name !== 'string' || !file.name || file.name.length > 160
            || /[\\/\x00-\x1f]/.test(file.name) || file.name === '.' || file.name === '..'
            || !Number.isSafeInteger(file.bytes) || file.bytes < 0
            || !/^[a-f0-9]{64}$/.test(file.sha256 || '')) throw new Error('The checked download list could not be read.');
      }
    }
    return data.bundles;
  }
  async function paintExampleDownloads(host, retry = false) {
    if (!host?.isConnected) return;
    if (retry) { exampleDownloads = null; exampleDownloadsRequest = null; }
    host.replaceChildren();
    const status = document.createElement('p'); status.className = 'hint'; status.setAttribute('role', 'status');
    status.textContent = 'Loading checked example downloads…'; host.append(status);
    try {
      if (!exampleDownloads) {
        if (!exampleDownloadsRequest) exampleDownloadsRequest = api(API + 'examples/artifacts').then(checkedDownloadBundles);
        exampleDownloads = await exampleDownloadsRequest;
      }
      if (!host.isConnected) return;
      host.replaceChildren();
      if (!exampleDownloads.length) { status.textContent = 'No checked downloads have been published yet.'; host.append(status); return; }
      for (const bundle of exampleDownloads) {
        const section = document.createElement('section'), heading = document.createElement('h2');
        heading.textContent = bundle.title; heading.style.fontSize = '16px'; section.append(heading);
        const zip = document.createElement('a'); zip.className = 'btn sm'; zip.textContent = 'Download complete bundle (ZIP)';
        zip.href = exampleDownloadUrl(bundle.id, 'bundle.zip'); zip.download = bundle.id + '.zip'; section.append(zip);
        const list = document.createElement('ul'); list.style.paddingLeft = '20px'; list.style.lineHeight = '1.8';
        for (const file of bundle.files) {
          const item = document.createElement('li'), link = document.createElement('a');
          link.href = exampleDownloadUrl(bundle.id, file.name); link.download = file.name; link.textContent = file.name;
          link.style.overflowWrap = 'anywhere'; link.title = 'SHA-256: ' + file.sha256;
          const size = document.createElement('span'); size.className = 'hint';
          size.textContent = ' · ' + (file.bytes < 1024 ? file.bytes + ' bytes' : (file.bytes / 1024).toFixed(1) + ' KiB');
          item.append(link, size); list.append(item);
        }
        section.append(list); host.append(section);
      }
    } catch (_) {
      exampleDownloadsRequest = null;
      if (!host.isConnected) return;
      status.textContent = 'Checked downloads are unavailable right now. Try again in a moment.';
      const button = document.createElement('button'); button.className = 'btn sm ghost'; button.textContent = 'Retry downloads';
      button.onclick = () => paintExampleDownloads(host, true); host.replaceChildren(status, button);
    }
  }

  // ---------------------------------------------------------------- page: write
  function renderWrite(m) {
    writeDiagnostics?.destroy(); writeDiagnostics = null;
    const ex = (META && META.examples) || [];
    m.innerHTML = `
      <div class="unit">
        <p class="hint" style="margin-bottom:14px"><a href="symblic-guides/index.html">New to Symblic? Start here</a> · examples, model teams, loops and waits</p>
        <div class="sy-top">
          <span class="sy-name" id="syName"></span><span class="sy-pill" id="syMode" hidden title="a .symd paper: prose is context, definitions are terms, fenced symblic blocks are the statements">paper</span>
          <select class="field" id="syEx" aria-label="Load an example"><option value="">Examples…</option>${ex.map((e) => `<option value="${att(e.id)}">${esc(e.name)}</option>`).join('')}</select>
          <select class="field" id="syProg" aria-label="Load a saved program"><option value="">Saved…</option>${(PROGRAMS || []).map((p) => `<option value="${att(p.name)}">${esc(p.name)}</option>`).join('')}</select>
          <button class="btn sm" id="sySave">Save</button>
          <button class="btn sm ghost" id="syNew">New</button>
        </div>
        <details id="syExampleDownloads" style="margin:14px 0" ${exampleDownloadsOpen ? 'open' : ''}>
          <summary>Checked example downloads</summary>
          <p class="hint">Download the checked artifacts and their verification records.</p>
          <div id="syExampleDownloadList"></div>
        </details>
        <div class="sy-native-layout">
          <div>
            <div class="sy-ed">
              <div class="sy-gut" id="syGut" aria-hidden="true"></div>
              <div class="sy-body">
                <pre class="sy-hl" id="syHl" aria-hidden="true"></pre>
                <textarea class="sy-src" id="sySrc" spellcheck="false" autocapitalize="off" autocomplete="off" wrap="off" aria-label="Symblic program"></textarea>
              </div>
            </div>
            <div class="sy-diag" id="syDiag"></div>
            <div id="syInlineDiagnostics"></div>
            <div class="sy-acts">
              <button class="btn acc" id="syRun" title="Ctrl+Enter">Run</button>
              <button class="btn" id="syPreview" title="Ctrl+Shift+Enter">Preview</button>
            </div>
            <div id="syOut" style="margin-top:16px"></div>
          </div>
          <details class="sy-native-settings" ${writeSettingsOpen ? 'open' : ''}>
            <summary>Agents and execution settings · ${esc(BY)}</summary>
            <span class="lbl">Who applies the asks</span>
            <div class="sy-apps" id="syApps"><span class="hint">Loading cached model choices…</span></div>
            <div class="fieldrow" style="margin-top:8px"><input class="field" id="syBy" value="${att(BY)}" aria-label="Applicator" placeholder="engine:model@node"></div>
            <button class="btn ghost" id="syPick" type="button" style="margin-top:8px">Choose agents…</button>
            <div class="hint" style="margin-top:6px">Agent CLIs and unpinned Ollama choices ran on the host's worker nodes. Models on the host machine itself are named explicitly with <code>@host</code>. A statement can name its own with <code>by=</code>; formal statements never need one.</div>
            <div class="sy-inputs" id="syInputs"></div>
            <label class="check" style="margin-top:12px"><input type="checkbox" id="syFx" ${SIDE ? 'checked' : ''}> Allow this run to start host agents (<code>delegate</code>)</label>
            <details style="margin-top:12px" ${STRICT_MODEL_PINS ? 'open' : ''}>
              <summary>Run model identity policy</summary>
              <label class="check"><input type="checkbox" id="syStrictPins" aria-describedby="syStrictPinsHelp" ${STRICT_MODEL_PINS ? 'checked' : ''} ${!strictModelPinsAvailable() && !STRICT_MODEL_PINS ? 'disabled' : ''}> Require matching recorded model identities</label>
              <p class="hint" id="syStrictPinsHelp">${strictModelPinsAvailable()
                ? 'Refuse model answers when model identity observations are missing, change or cannot be checked. Dispatched calls still count against the budget. These are host manifest observations, not loaded-weight attestations.'
                : 'This server does not support the strict policy. A selected strict policy blocks Run until the server supports it or you clear the selection.'}</p>
            </details>
            <details style="margin-top:12px" id="syCtorBox" ${CTOR.on ? 'open' : ''}>
              <summary>Checked construction</summary>
              <label class="check"><input type="checkbox" id="syCtorOn" aria-describedby="syCtorHelp syCtorWhy"> Construct exact answers before asking a model</label>
              <p class="hint" id="syCtorHelp">An <code>ask</code> for a Bool, Int or fraction value that its <code>ensure</code> checks pin down with linear constraints (sums, constant multiples, comparisons) can be constructed and checked with no model. Without ensure checks there is nothing to construct from. Free-form questions keep their ordinary path; one checked value does not show it is the only answer.</p>
              <p class="hint" id="syCtorWhy" role="status" style="margin-top:6px"></p>
              <details id="syCtorAdv" style="margin-top:8px">
                <summary>Advanced: mode and model fallback</summary>
                <label class="lbl" for="syCtorMode" style="margin-top:8px">Mode</label>
                <select class="field" id="syCtorMode">
                  <option value="linear">Bind checked values (linear)</option>
                  <option value="linear_diagnose">Diagnose only: record candidates, models still answer (linear_diagnose)</option>
                </select>
                <label class="lbl" for="syCtorCalls" style="margin-top:8px">Model calls allowed for this run (0 to 10000)</label>
                <input class="field" id="syCtorCalls" inputmode="numeric" autocomplete="off" spellcheck="false" aria-describedby="syCtorCallsHelp syCtorErr">
                <p class="hint" id="syCtorCallsHelp">0 means none: an ask the constructor cannot build fails the run visibly instead of reaching a model. Attempts, time and solver work stay within the server's fixed bounds.</p>
                <p class="hint" id="syCtorErr" role="alert" style="color:var(--err)"></p>
              </details>
            </details>
            <div class="sy-acts">
              <button class="btn" id="syCmp">Compare agents…</button>
              <button class="btn" id="syTighten" title="Ask several agents, find the statements they read differently, and rewrite them">Tighten…</button>
              <button class="btn" id="syTests" hidden title="Run the program's test blocks with the kernel">Run tests</button>
              <button class="btn" id="syCryst" hidden title="Compile a routine's agreed answers into an exact kernel table">Crystallise…</button>
              <button class="btn ghost" id="syStudio" title="Open the Studio canvas with this program as a workflow step">Send to Studio</button>
            </div>
            <p class="hint">Source errors are underlined. Click a problem or press F8 to inspect it. Source checks do not run your program.</p>
          </details>
        </div>
      </div>`;
    const downloads = $('syExampleDownloads');
    downloads.addEventListener('toggle', () => {
      exampleDownloadsOpen = downloads.open;
      if (downloads.open) paintExampleDownloads($('syExampleDownloadList'));
    });
    if (downloads.open) paintExampleDownloads($('syExampleDownloadList'));
    m.querySelector('.sy-native-settings').addEventListener('toggle', event => { writeSettingsOpen = event.target.open; });
    const ta = $('sySrc'), hl = $('syHl'), gut = $('syGut');
    ta.value = SRC;
    writeDiagnostics = window.SymblicEditorDiagnostics?.attach(ta, { problems: $('syInlineDiagnostics'), label: 'Program diagnostics' }) || null;
    const paint = () => {
      hl.innerHTML = highlight(ta.value);
      const lines = ta.value.split('\n').length;
      if (gut.childElementCount !== lines) {
        gut.innerHTML = Array.from({ length: lines }, (_, k) => `<b data-l="${k + 1}">${k + 1}</b>`).join('');
        markGutter();
      }
    };
    paintCtor();
    const sync = () => { hl.scrollTop = ta.scrollTop; hl.scrollLeft = ta.scrollLeft; gut.scrollTop = ta.scrollTop; };
    ta.addEventListener('input', () => { SRC = ta.value; saveDraft(); paint(); paintCtor(); scheduleCheck(); });
    ta.addEventListener('scroll', sync);
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Tab' && !e.shiftKey) {
        e.preventDefault();
        const s = ta.selectionStart, en = ta.selectionEnd;
        ta.setRangeText('  ', s, en, 'end');
        ta.dispatchEvent(new Event('input'));
      } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (e.shiftKey) doPreview(); else doRun();
      }
    });
    paint();
    $('syEx').onchange = (e) => {
      const it = ex.find((x) => x.id === e.target.value);
      if (it && (!SRC.trim() || SRC === STARTER || confirm('Replace the program in the editor with this example?'))) {
        SRC = it.source; ta.value = SRC; saveDraft(); paint(); runCheck(); PREVIEW = null; paintOut();
      }
      e.target.value = '';
    };
    $('syProg').onchange = (e) => {
      const it = (PROGRAMS || []).find((x) => x.name === e.target.value);
      if (it && (!SRC.trim() || confirm('Replace the program in the editor with "' + it.name + '"?'))) {
        SRC = it.source; ta.value = SRC; saveDraft(); paint(); runCheck();
      }
      e.target.value = '';
    };
    $('sySave').onclick = async () => {
      const name = prompt('Save as', (CHECK && CHECK.name) || '');
      if (!name) return;
      try { await api(API + 'programs/save', { name, source: SRC }); toast('Saved'); await loadPrograms(); Studio.repaint(); }
      catch (e) { toast(e.message); }
    };
    $('syNew').onclick = () => {
      if (SRC.trim() && !confirm('Start a new program? The editor is cleared (save first to keep this one).')) return;
      SRC = 'program Untitled.\n\n'; ta.value = SRC; saveDraft(); paint(); runCheck();
    };
    m.querySelectorAll('[data-by]').forEach((b) => {
      b.onclick = () => { setBy(b.dataset.by); };
    });
    $('syBy').onchange = (e) => setBy(e.target.value.trim());
    if (window.SymblicPicker?.mountChoices) window.SymblicPicker.mountChoices($('syApps'), { getValue: () => BY, onSelect: setBy });
    else $('syApps').textContent = 'The model picker did not load. Reload the page, or enter an applicator below.';
    $('syPreview').onclick = doPreview;
    $('syRun').onclick = doRun;
    $('syCmp').onclick = openCompareSheet;
    $('syTighten').onclick = openTightenSheet;
    $('syCryst').onclick = openCrystalSheet;
    $('syTests').onclick = doTests;
    $('syStudio').onclick = sendToStudio;
    $('syFx').onchange = (e) => { SIDE = e.target.checked; };
    $('syStrictPins').onchange = (e) => {
      setStrictModelPins(e.target.checked);
      e.target.disabled = !strictModelPinsAvailable() && !STRICT_MODEL_PINS;
    };
    $('syCtorMode').value = CTOR.mode;
    $('syCtorCalls').value = CTOR.calls;
    $('syCtorOn').onchange = (e) => { CTOR = { ...CTOR, on: e.target.checked }; saveCtor(); paintCtor(); };
    $('syCtorMode').onchange = (e) => { CTOR = { ...CTOR, mode: CTOR_MODES.includes(e.target.value) ? e.target.value : 'linear' }; saveCtor(); };
    $('syCtorCalls').oninput = (e) => { CTOR = { ...CTOR, calls: e.target.value.trim().slice(0, 12) }; saveCtor(); paintCtor(); };
    paintCtor();
    if (CHECK && checkedSource === SRC && diagnosticSource === ta.value) { paintDiag(); paintInputs(); $('syName').textContent = CHECK.name || ''; $('syMode').hidden = !isPaper(SRC); paintTestsButton(); } else runCheck();
    paintOut();
  }

  // The checked-construction controls follow the editor: a paper, a bound task or a server without the marker turns
  // them off with the reason; a selection the server cannot honour stays visible so it can be cleared.
  function paintCtor() {
    const on = $('syCtorOn');
    if (!on) return;
    const block = ctorBlock(), held = block === 'unavailable' && CTOR.on;
    on.checked = CTOR.on && (!block || held);
    on.disabled = !!block && !held;
    $('syCtorMode').disabled = $('syCtorCalls').disabled = !!block;
    $('syCtorWhy').textContent = block ? CTOR_REASONS[block] : '';
    $('syCtorWhy').hidden = !block;
    const bad = !block && CTOR.on && ctorCalls() === null;
    $('syCtorErr').textContent = bad ? 'Enter a whole number from 0 to 10000.' : '';
    $('syCtorCalls').setAttribute('aria-invalid', bad ? 'true' : 'false');
    if (bad) $('syCtorAdv').open = true;
  }

  function sendToStudio() {
    // the Studio canvas picks this up on load (automation-studio/js/ui.js maybeLoadSymblicWorkflow)
    const name = (CHECK && CHECK.name) || 'Symblic program';
    const graph = {
      nodes: {
        start: { id: 'start', type: 'start', title: 'Start', x: 120, y: 140, data: {} },
        symblic: { id: 'symblic', type: 'symblic', title: name.slice(0, 40), x: 380, y: 140, data: { source: SRC, by: BY } },
      },
      edges: [{ from: 'start', to: 'symblic', label: '' }],
    };
    try { localStorage.setItem('symblicWorkflow', JSON.stringify({ name, graph })); } catch (_) { toast('Could not hand it over'); return; }
    location.href = 'index.html';
  }

  function setBy(v) {
    BY = v || 'claude:haiku';
    try { localStorage.setItem(BY_KEY, BY); } catch (_) { }
    document.querySelectorAll('#syApps [data-by]').forEach((b) => b.classList.toggle('on', b.dataset.by === BY));
    window.SymblicPicker?.syncChoices?.();
    const f = $('syBy');
    if (f && f.value !== BY) f.value = BY;
  }

  function markGutter() {
    const gut = $('syGut');
    if (!gut || !CHECK) return;
    gut.querySelectorAll('b').forEach((b) => b.classList.remove('err', 'warn'));
    const diagnostics = diagnosticReport && checkedSource === SRC ? diagnosticReport.diagnostics : null;
    const warnings = diagnostics ? diagnostics.filter(d => d.severity === 'warning') : CHECK.warnings || [];
    const errors = diagnostics ? diagnostics.filter(d => d.severity === 'error') : CHECK.errors || [];
    for (const w of warnings) { const b = gut.querySelector(`[data-l="${+w.line}"]`); if (b) b.classList.add('warn'); }
    for (const e of errors) { const b = gut.querySelector(`[data-l="${+e.line}"]`); if (b) b.classList.add('err'); }
  }

  function paintDiag() {
    const el = $('syDiag');
    if (!el || !CHECK) return;
    markGutter();
    const precise = diagnosticReport && checkedSource === SRC && writeDiagnostics;
    if (precise) writeDiagnostics.setDiagnostics(diagnosticSource, diagnosticReport.diagnostics || []);
    else writeDiagnostics?.clear('Inline ranges are unavailable; source checks are shown here.');
    const rows = precise ? [] : diagnosticReport ? (diagnosticReport.diagnostics || []).map(d => [d.severity === 'error' ? 'err' : 'warn', d])
      : [...(CHECK.errors || []).map((e) => ['err', e]), ...(CHECK.warnings || []).map((w) => ['warn', w])];
    const prof = CHECK.profile || {};
    const total = Object.values(prof).reduce((a, b) => a + b, 0) || 1;
    const order = ['exact', 'closed', 'structured', 'open', 'observed', 'effect'];
    el.innerHTML = `
      ${CHECK.ok ? `<div class="hint">${pill('good', 'checks')} ${esc((CHECK.plan || []).length + ' statements · ' + (CHECK.asks || 0) + ((CHECK.asks || 0) === 1 ? ' ask' : ' asks'))}</div>` : ''}
      <div class="sy-prof" title="determinism profile">${order.filter((k) => prof[k]).map((k) => `<i class="${k}" style="width:${(100 * prof[k] / total).toFixed(1)}%"></i>`).join('')}</div>
      <div class="hint">${order.filter((k) => prof[k]).map((k) => pill(k, prof[k] + ' ' + k)).join(' ')}</div>
      ${CHECK.ok && (CHECK.asks_detail || []).length ? `<details class="sy-pred"><summary class="hint">Predictability ${+CHECK.predictability} / 100 · a guide from the text alone (Tighten measures it with agents)</summary>
        ${(CHECK.asks_detail || []).filter((d) => (d.reasons || []).length).map((d) => `<div class="d warn" data-line="${+d.line || 0}"><span class="ln">line ${+d.line} · ${esc(d.name)} · ${+d.score}</span><span>${esc(d.reasons.join('; '))}</span></div>`).join('')}</details>` : ''}
      ${rows.map(([k, d]) => `<div class="d ${k}" data-line="${+d.line || 0}"><span class="ln">${d.line ? 'line ' + (+d.line) : ''}</span><span>${esc(d.message)}</span></div>`).join('')}`;
    el.querySelectorAll('[data-line]').forEach((d) => { d.onclick = () => goLine(+d.dataset.line); });
  }

  function goLine(n) {
    const ta = $('sySrc');
    if (!ta || !n) return;
    const lines = ta.value.split('\n');
    let pos = 0;
    for (let k = 0; k < n - 1 && k < lines.length; k++) pos += lines[k].length + 1;
    ta.focus();
    ta.setSelectionRange(pos, pos + (lines[n - 1] || '').length);
    ta.scrollTop = Math.max(0, (n - 4) * 24);
  }

  function paintInputs() {
    const el = $('syInputs');
    if (!el) return;
    const gives = ((CHECK && CHECK.plan) || []).filter((r) => r.kind === 'given');
    if (!gives.length) { el.innerHTML = ''; return; }
    el.innerHTML = `<span class="lbl" style="margin-top:14px">Inputs</span>` + gives.map((g) => `
      <label>${esc(g.binds)} <span class="sy-pill">${esc(g.type || 'any')}</span>${g.required ? ' ' + pill('bad', 'required') : ' <span class="hint">empty = the default</span>'}
        <textarea class="field" rows="2" data-input="${att(g.binds)}">${esc(INPUTS[g.binds] || '')}</textarea></label>`).join('');
    el.querySelectorAll('[data-input]').forEach((t) => { t.oninput = () => { INPUTS[t.dataset.input] = t.value; saveDraft(); }; });
  }

  function inputsPayload() {
    const out = {};
    for (const [k, v] of Object.entries(INPUTS)) {
      if (String(v).trim() === '') continue;
      const s = String(v).trim();
      try { out[k] = /^[\[{]|^-?\d|^(true|false)$/.test(s) ? JSON.parse(s) : v; } catch (_) { out[k] = v; }
    }
    return out;
  }

  async function doPreview() {
    if (BUSY) return;
    BUSY = true;
    PREVIEW = { loading: true }; paintOut();
    try {
      const source = isPaper(SRC) ? (await api(API + 'paper/compile', { source: SRC })).source : SRC;
      PREVIEW = await api(API + 'preview', { source, inputs: inputsPayload(), by: BY });
    }
    catch (e) { PREVIEW = { error: e.message }; }
    BUSY = false;
    paintOut();
  }

  async function doRun() {
    if (BUSY) return;
    if (CHECK && !CHECK.ok) { toast('Fix the errors first'); return; }
    if (STRICT_MODEL_PINS && !strictModelPinsAvailable()) { toast('Strict model identities require a server update. Your selection has been retained.'); return; }
    const ctorSkip = CTOR.on ? ctorBlock() : '';
    if (ctorSkip === 'unavailable') { toast('Checked construction needs a server update. Clear it or update the server; no run was started.'); return; }
    if (CTOR.on && !ctorSkip && ctorCalls() === null) { toast('Model calls must be a whole number from 0 to 10000; no run was started.'); paintCtor(); return; }
    BUSY = true;
    try {
      const options = { ...(SRC === TASK_SOURCE ? TASK_OPTIONS : {}), side_effects: SIDE };
      delete options.model_pins;
      if (STRICT_MODEL_PINS) options.model_pins = 'strict';
      if (CTOR.on && !ctorSkip) Object.assign(options, { constructor: CTOR.mode, determine: false, solve: false, max_calls: ctorCalls() });
      const res = await api(API + (isPaper(SRC) ? 'paper/run' : 'run'), { source: SRC, inputs: inputsPayload(), by: BY, title: (CHECK && CHECK.name) || '',
        options });
      toast(ctorSkip === 'paper' ? 'Started without checked construction: it applies to native programs'
        : ctorSkip === 'bound' ? "Started with the task's prepared policy" : 'Started');
      OPEN = null; OPEN_ID = res.id;
      await loadRuns();
      Studio.go('runs');
    } catch (e) { toast(e.message); }
    BUSY = false;
  }

  async function doTests() {
    if (BUSY) return;
    BUSY = true;
    PREVIEW = { loading: true }; paintOut();
    try { PREVIEW = { tests: await api(API + 'tests', { source: SRC }) }; } catch (e) { PREVIEW = { error: e.message }; }
    BUSY = false;
    paintOut();
  }

  function testsHtml(r) {
    return `<span class="lbl">Tests · ${+r.passed || 0} passed, ${+r.failed || 0} failed, ${+r.inconclusive || 0} inconclusive</span>
      ${r.error ? `<div class="card">${pill(['resource', 'unavailable'].includes(r.error.kind) ? 'structured' : 'bad', 'line ' + (+(r.error.line || 0)))} ${esc(r.error.message || '')}</div>` : ''}
      <div class="rows">${(r.tests || []).map((t) => `<div class="row"><div class="grow"><div class="ttl">${pill(t.status === 'passed' ? 'good' : t.status === 'inconclusive' ? 'structured' : 'bad', t.status)} ${esc(t.title)}</div>
        ${t.error ? `<div class="sub">line ${+(t.error.line || 0)}: ${esc(t.error.message || '')}</div>` : ''}</div><span class="hint">line ${+t.line}</span></div>`).join('') || '<div class="empty">No tests.</div>'}</div>
      <div class="hint">Tests here use the kernel only; a test that asks a model is certified from a terminal (bin/symblic certify).</div>`;
  }

  function paintOut() {
    const el = $('syOut');
    if (!el) return;
    const p = PREVIEW;
    if (!p) { el.innerHTML = '<div class="hint">Preview runs the formal statements and stops at the first ask to show exactly what the agent would be sent. Nothing reaches a model.</div>'; return; }
    if (p.loading) { el.innerHTML = busy; return; }
    if (p.error) { el.innerHTML = `<div class="empty">${esc(p.error)}</div>`; return; }
    if (p.tests) { el.innerHTML = testsHtml(p.tests); return; }
    const err = p.error_message || (p.error && p.error.message);
    el.innerHTML = `
      <span class="lbl">Preview · ${esc(p.status)}${p.status === 'paused' ? ' at the first ask' : ''}</span>
      ${p.error ? `<div class="card">${pill('bad', 'line ' + (p.error.line || 0))} ${esc(p.error.message || '')}</div>` : ''}
      ${(p.bindings || []).length ? `<div class="rows">${p.bindings.map((b) => `<div class="row"><div class="grow"><div class="ttl mono">${esc(b.name)} <span class="sy-pill">${esc(b.type)}</span></div><div class="sub">${esc(typeof b.value === 'string' ? b.value : JSON.stringify(b.value))}</div></div>${swatch(b.hash)}</div>`).join('')}</div>` : ''}
      ${(p.outputs || []).map((o) => `<div class="card"><span class="lbl">${esc(o.kind)} ${esc(o.label || '')}</span><div class="mono">${esc(o.text || '')}</div>${swatch(o.hash)}</div>`).join('')}
      ${p.drawing ? `<div class="sy-draw"><figure><img alt="drawing" data-svg="1"><figcaption>kernel drawing</figcaption></figure></div>` : ''}
      ${p.next ? `<div class="card"><span class="lbl">What ${esc(p.next.app)} would be sent for <b>${esc(p.next.name)}</b> (line ${+p.next.line})</span>
          <div class="hint">System</div><div class="codeblock sy-cap">${esc(p.next.system)}</div>
          <div class="hint" style="margin-top:8px">Statement capsule</div><div class="codeblock sy-cap">${esc(p.next.prompt)}</div>
          <div class="hint" style="margin-top:8px">Answer schema (enforced where the engine supports it)</div><div class="codeblock sy-cap">${esc(JSON.stringify(p.next.schema, null, 1))}</div></div>` : ''}
      <div class="hint">fingerprint so far ${swatch(p.fingerprint)}</div>`;
    if (p.drawing) setSvg(el.querySelector('img[data-svg]'), p.drawing);
    void err;
  }

  function setSvg(img, svg) {
    if (!img) return;
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
    img.onload = () => URL.revokeObjectURL(url);
    img.src = url;
  }

  // ---------------------------------------------------------------- compare sheet
  function openCompareSheet() {
    if (CHECK && !CHECK.ok) { toast('Fix the errors first'); return; }
    const veil = document.createElement('div');
    veil.className = 'veil on';
    const sheet = document.createElement('div');
    sheet.className = 'sheet on';
    sheet.setAttribute('role', 'dialog');
    sheet.innerHTML = `<span class="lbl">Compare agents</span>
      <p class="hint">The same program runs once per agent you tick. The comparison lines up every statement's fingerprint: identical colours mean identical canonical results.</p>
      <div class="sy-sheet-apps">${APPS.filter(([v]) => !v.startsWith('council')).map(([v, t]) => `<label><input type="checkbox" value="${att(v)}" ${['claude:haiku', 'codex', 'ollama:qwen3:4b-instruct', 'ollama:llama3.2:1b'].includes(v) ? 'checked' : ''}> ${esc(t)}</label>`).join('')}</div>
      <div class="sy-acts"><button class="btn acc" id="syCmpGo">Run comparison</button><button class="btn ghost" id="syCmpX">Cancel</button></div>`;
    document.body.append(veil, sheet);
    const close = () => { veil.remove(); sheet.remove(); };
    veil.onclick = close;
    sheet.querySelector('#syCmpX').onclick = close;
    sheet.querySelector('#syCmpGo').onclick = async () => {
      const apps = [...sheet.querySelectorAll('input:checked')].map((c) => c.value);
      if (apps.length < 2) { toast('Tick at least two'); return; }
      try {
        const res = await api(API + (isPaper(SRC) ? 'paper/reproduce' : 'compare'), { source: SRC, inputs: inputsPayload(), applicators: apps, title: (CHECK && CHECK.name) || 'comparison' });
        close();
        toast('Comparison started');
        CMP = null; CMP_ID = res.id;
        await loadCmps();
        Studio.go('compare');
      } catch (e) { toast(e.message); }
    };
  }

  // ---------------------------------------------------------------- tighten sheet and page
  const TIGHTEN_PANEL = ['claude:haiku', 'codex', 'agy', 'ollama:qwen3:4b-instruct', 'ollama:llama3.2:1b'];
  function openTightenSheet() {
    if (CHECK && !CHECK.ok) { toast('Fix the errors first'); return; }
    if (isPaper(SRC)) { toast('Tighten works on a program; compile the paper first (bin/symblic paper compile)'); return; }
    const veil = document.createElement('div');
    veil.className = 'veil on';
    const sheet = document.createElement('div');
    sheet.className = 'sheet on';
    sheet.setAttribute('role', 'dialog');
    sheet.innerHTML = `<span class="lbl">Tighten with agents</span>
      <p class="hint">Every ask is answered by each agent you tick, with a fresh context, and each lists the readings it sees. Where they disagree or see two readings, the clarifier rewrites the statement with explicit assumptions (never the answer), and the agents answer again. Runs on the worker nodes; small models take minutes.</p>
      <div class="sy-sheet-apps">${APPS.filter(([v]) => !v.startsWith('council')).map(([v, t]) => `<label><input type="checkbox" value="${att(v)}" ${TIGHTEN_PANEL.includes(v) ? 'checked' : ''}> ${esc(t)}</label>`).join('')}</div>
      <div class="fieldrow" style="margin-top:10px"><label class="hint" for="syClar">Clarifier</label>
        <select class="field" id="syClar">${['claude:sonnet', 'claude:opus', 'codex'].map((v) => `<option value="${att(v)}">${esc(v)}</option>`).join('')}</select></div>
      <div class="sy-acts"><button class="btn acc" id="syTGo">Start</button><button class="btn ghost" id="syTX">Cancel</button></div>`;
    document.body.append(veil, sheet);
    const close = () => { veil.remove(); sheet.remove(); };
    veil.onclick = close;
    sheet.querySelector('#syTX').onclick = close;
    sheet.querySelector('#syTGo').onclick = async () => {
      const panel = [...sheet.querySelectorAll('input:checked')].map((c) => c.value);
      if (panel.length < 2) { toast('Tick at least two'); return; }
      try {
        const res = await api(API + 'tighten', { source: SRC, inputs: inputsPayload(), panel, clarifier: sheet.querySelector('#syClar').value, title: (CHECK && CHECK.name) || 'program' });
        close();
        toast('Tightening started');
        TJOB = null; TJOB_ID = res.id;
        await loadTightens();
        Studio.go('tighten');
      } catch (e) { toast(e.message); }
    };
  }

  const DIAG = { converged: 'good', ambiguous: 'bad', divergent: 'bad', capability: 'structured', format: 'bad', unreached: 'open', failed: 'bad' };
  function renderTighten(m) {
    if (!TJOBS) { m.innerHTML = busy; loadTightens().then(() => Studio.repaint()); return; }
    if (TJOB_ID && (!TJOB || TJOB.id !== TJOB_ID)) { m.innerHTML = busy; loadTighten(TJOB_ID).then(() => Studio.repaint()); return; }
    if (TJOB) { renderTightenJob(m, TJOB); return; }
    m.innerHTML = `<div class="unit"><span class="lbl">Tightening</span>
      <p class="hint">Write a program, then press Tighten… on the Write screen. Each tightening asks a panel of agents every ask, finds the statements they read differently, and rewrites them.</p>
      ${TJOBS.length ? `<div class="rows">${TJOBS.map((r) => `<div class="row tap" data-tj="${att(r.id)}">
        <span class="dot ${r.status === 'running' ? 'on' : r.status === 'done' ? 'ok' : 'err'}"></span>
        <div class="grow"><div class="ttl">${esc(r.title || r.id)}</div><div class="sub">${esc([r.status, (r.panel || []).join(', '), when(r.created)].filter(Boolean).join(' · '))}</div></div></div>`).join('')}</div>` : '<div class="empty">None yet.</div>'}</div>`;
    m.querySelectorAll('[data-tj]').forEach((r) => { r.onclick = () => { TJOB_ID = r.dataset.tj; TJOB = null; Studio.repaint(); }; });
  }

  function renderTightenJob(m, v) {
    const res = v.result || {};
    const hist = res.history || [];
    const candidate = res.candidate_program || res.program || '';
    const fidelity = res.fidelity || {};
    const audited = res.version === 2 && !!res.audit_sha256;
    const round = (h) => `<div class="card"><span class="lbl">Round ${+h.round} · ${h.round ? 'after rewriting' : 'as written'} · mean agreement ${Math.round(100 * (+h.agreement_all || 0))}%</span>
      <div class="rows">${(h.asks || []).map((a) => `<div class="row"><div class="grow"><div class="ttl mono">line ${+a.line} · ${esc(a.name || '')} ${pill(DIAG[a.diagnosis] || '', a.diagnosis)}</div>
        <div class="sub">agreement ${Math.round(100 * (+a.agreement_all || 0))}% · ${+a.distinct || 0} distinct answer(s)${(a.flagged || []).length ? ' · readings seen by ' + esc(a.flagged.join(', ')) : ''}${(a.missing || []).length ? ' · not reached: ' + esc(a.missing.join(', ')) : ''}</div>
        ${(a.readings || []).length ? `<div class="sub">readings: ${esc(a.readings.slice(0, 6).join(' · '))}</div>` : ''}
        ${(a.suggestions || []).length ? `<div class="sub">${esc(a.suggestions.join('; '))}</div>` : ''}</div></div>`).join('')}</div></div>`;
    const rw = (r) => `<div class="card"><span class="lbl">Line ${+r.line} · ${esc(r.name || '')} ${r.leaks_answer ? pill('bad', 'refused: names the answer') : r.ok ? pill('good', 'proposed') : pill('bad', 'no rewrite')}</span>
      <div class="hint">before</div><div class="codeblock">${esc(r.before || '')}</div>
      ${r.instruction ? `<div class="hint" style="margin-top:6px">after</div><div class="codeblock">${esc(r.instruction)}</div>` : ''}
      ${(r.assumptions || []).length ? `<div class="hint" style="margin-top:6px">assumptions: ${esc(r.assumptions.join(' · '))}</div>` : ''}
      ${r.error ? `<div class="hint">${esc(r.error)}</div>` : ''}</div>`;
    m.innerHTML = `
      <div class="unit"><button class="btn sm ghost" id="syTBack">← all tightenings</button></div>
      <div class="unit"><span class="lbl">${esc(v.title || v.id)} · ${esc(v.status)}</span>
        <div class="hint">panel ${esc((v.panel || []).join(', '))} · clarifier ${esc(v.clarifier || '')} · ${esc(when(v.created))}</div>
        <div class="sy-acts">${v.status === 'running' ? '<button class="btn danger sm" id="syTStop">Stop</button>' : ''}
          ${res.changed ? '<button class="btn acc sm" id="syTUse">Review candidate in the editor</button>' : ''}
          <button class="btn sm ghost" id="syTOrig">Open the original</button>
          ${res.changed && audited && v.status === 'done' ? '<button class="btn sm" id="syTAdopt">Adopt this exact candidate</button>' : ''}</div>
        <p class="hint">Candidate rewrites are proposals. Fidelity: ${esc(fidelity.status || 'not assessed')}. Passing finite checks does not establish preserved meaning.</p>
        ${(fidelity.requirements || []).length ? `<div class="rows">${fidelity.requirements.map(r => `<div class="row"><span>${esc(r.id)} · ${esc(r.text)} · ${esc(r.status)}</span></div>`).join('')}</div>` : ''}
        ${v.adoption && v.adoption.adoption ? `<p class="hint">Saved owner choice: ${esc(v.adoption.adoption.status)}</p>` : ''}
        ${res.error ? `<div class="card">${pill('bad', 'failed')} ${esc(res.error)}</div>` : ''}
        ${v.status === 'done' && !res.changed ? '<div class="hint">No candidate change was produced.</div>' : ''}</div>
      ${hist.length ? `<div class="unit">${hist.map(round).join('')}</div>` : (v.status === 'running' ? busy : '')}
      ${(res.rewrites || []).length ? `<div class="unit"><span class="lbl">Rewrites</span>${res.rewrites.map(rw).join('')}</div>` : ''}
      ${res.changed ? `<div class="unit"><span class="lbl">Proposed candidate</span><div class="codeblock">${esc(candidate)}</div></div>` : ''}
      <div class="unit"><span class="lbl">Log</span><div class="codeblock">${esc(v.log || '')}</div>
        <p class="hint">Agreement is not correctness, and a rewrite is judged fairly only by agents that took no part in making it (python3 -m symblic.bench.bench --suite tighten).</p></div>`;
    const open = (text) => { if (!SRC.trim() || confirm('Replace the program in the editor?')) { SRC = text; saveDraft(); CHECK = null; Studio.go('write'); } };
    $('syTBack').onclick = () => { TJOB = null; TJOB_ID = ''; loadTightens().then(() => Studio.repaint()); };
    if ($('syTStop')) $('syTStop').onclick = async () => { try { await api(API + 'tighten/stop', { id: v.id }); await loadTighten(v.id); Studio.repaint(); } catch (e) { toast(e.message); } };
    if ($('syTUse')) $('syTUse').onclick = () => open(candidate);
    if ($('syTAdopt')) $('syTAdopt').onclick = async () => {
      try {
        await api(API + 'tighten/adopt', { id: v.id, original_sha256: res.original_sha256, candidate_sha256: res.candidate_sha256, audit_sha256: res.audit_sha256 });
        await loadTighten(v.id); Studio.repaint(); toast('Exact candidate adopted');
      } catch (e) { toast(e.message); }
    };
    $('syTOrig').onclick = () => open(v.source || '');
  }

  // ---------------------------------------------------------------- page: plan
  function renderPlan(m) {
    if (!CHECK) { m.innerHTML = busy; runCheck().then(() => Studio.repaint()); return; }
    const plan = CHECK.plan || [];
    m.innerHTML = `
      <div class="unit"><span class="lbl">${esc(CHECK.name || 'Program')} · ${plan.length} statements</span>
        <p class="hint">Every statement, in order, with what it binds, what it reads and how its result is decided. <b>exact</b>: the kernel computes it (identical everywhere). <b>closed</b>: a model picks from a small finite set. <b>structured</b>: a model gives a canonical number, list or record. <b>open</b>: free text. <b>effect</b>: starts something.</p></div>
      <div class="unit"><div class="tblwrap"><table class="tbl"><thead><tr><th>line</th><th>statement</th><th>class</th><th>type</th><th>reads</th><th>options</th></tr></thead><tbody>
        ${plan.map((r) => `<tr><td class="num">${+r.line}</td><td class="mono" style="padding-left:${12 + 14 * (r.depth || 0)}px">${esc(r.label)}${r.prompt ? `<div class="hint">${esc(r.prompt)}</div>` : ''}</td>
          <td>${r.class ? pill(r.class, r.class) : ''}</td><td class="mono">${esc(r.type || '')}</td><td class="mono">${esc((r.reads || []).join(', '))}</td>
          <td class="mono">${esc(Object.entries(r.options || {}).map(([k, v]) => k + '=' + v).join(', '))}${r.each ? esc(' each ' + r.each) : ''}</td></tr>`).join('')}
      </tbody></table></div></div>`;
  }

  // ---------------------------------------------------------------- page: runs
  function renderBuild(m) {
    const local = APPS.filter(([id]) => id.startsWith('ollama:'));
    const info = SHEET_INFO;
    if (!RUNS) loadRuns().then(() => { if (RUNS) Studio.repaint(); });
    const builds = (RUNS || []).filter((r) => r.spec);
    m.innerHTML = `<div class="unit"><span class="lbl">Build a file from a spec sheet</span>
      <p class="hint">A spec sheet describes one file as small units of code, each with a contract and examples. It compiles
        into a Symblic program with no model involved. Every unit is written in a fresh context by the models ticked
        below, tested against its examples by the kernel's sandboxed JavaScript, and repaired with the failing examples
        until it passes. The file is assembled only from units that passed. The format is in docs/symblic/SPEC-SHEETS.md.</p>
      <div class="sy-actions"><button class="btn sm" id="syExample">Load the Tetris sheet</button>
        <button class="btn sm" id="syCheckSheet">Check</button></div>
      <label style="display:block;margin-top:12px">Build method
        <select class="field" id="syBuildMode" style="font-size:16px;display:block;max-width:100%">
          <option value="legacy" ${BUILD_MODE === 'legacy' ? 'selected' : ''}>Sequential sheet with leading-unit reuse</option>
          <option value="task-cards" ${BUILD_MODE === 'task-cards' ? 'selected' : ''}>Task cards with dependency-aware reuse</option>
        </select></label>
      ${BUILD_MODE === 'task-cards' ? `<p class="hint">Each fresh request carries the complete declared dependency chain.
        Units pass isolated and combined-code checks. JavaScript files also recheck the final template output.
        HTML layout and behavior need separate browser checks. Edits rebuild affected branches while unchanged branches can be kept.</p>
        <label>Task presentation
          <select class="field" id="syBuildPresentation" style="font-size:16px;display:block;max-width:100%">
            <option value="compact" ${BUILD_PRESENTATION === 'compact' ? 'selected' : ''}>Compact task instructions</option>
            <option value="full" ${BUILD_PRESENTATION === 'full' ? 'selected' : ''}>Full task-card representation</option>
          </select></label>
        <details style="margin-top:12px"><summary>Declaration requirements (optional)</summary>
          <p class="hint">Require exact top-level names and kinds, with passive initialization. Function bodies still need their behavior checks. Blank keeps the existing JavaScript acceptance rules.</p>
          <button class="btn sm" id="syDeclarationTemplate">Prepare a function-only template</button>
          <label style="display:block;margin-top:10px">Declaration contracts by unit ID
            <textarea class="field" id="syBuildDeclarations" rows="6" style="font-size:16px;width:100%">${esc(BUILD_DECLARATIONS)}</textarea></label>
          <p class="hint">The template marks every named binding as a function. Edit individual kinds to class, const, let or var to match your specification before building.</p>
        </details>
        <label>Context limit per request (characters, including system and schema)
          <input class="field" id="syBuildBudget" type="number" min="1" max="262144" step="1"
            style="font-size:16px;display:block" value="${att(String(BUILD_BUDGET))}"></label>
        <label style="display:block;margin-top:10px">Import a portable build manifest
          <input id="syBuildManifest" type="file" accept="application/json,.json" style="font-size:16px;display:block;max-width:100%"></label>
        ${BUILD_MANIFEST ? `<p class="hint">Imported ${esc(BUILD_MANIFEST.output.file)} · output SHA-256
          <span style="overflow-wrap:anywhere">${esc(BUILD_MANIFEST.output.sha256)}</span>. Kept code is checked again locally.</p>
          <button class="btn sm" id="syClearManifest">Clear imported manifest</button>` : ''}` : ''}
      <textarea id="sySheet" spellcheck="false" autocapitalize="off" aria-label="spec sheet"
        style="width:100%;min-height:340px;box-sizing:border-box;font-family:var(--mono);font-size:16px;line-height:22px;margin-top:8px"
        placeholder="# file.html&#10;&#10;## Shared&#10;...&#10;&#10;## Unit \`name(args)\`&#10;...&#10;Examples:&#10;&#10;    name(1) ==> 2&#10;&#10;## Assemble \`file.html\`&#10;&#10;    ... /*UNITS*/ ..."></textarea>
      <div id="sySheetInfo">${info ? (info.ok
        ? `<div class="hint">${esc(info.title)}: ${info.units.length} units, ${info.units.reduce((n, u) => n + u.examples, 0)} examples, builds ${esc(info.file)}.${info.plan ? ` ${info.plan.layers.length} dependency layers.` : ''}</div>`
        : `<div class="hint">Does not compile yet:</div><ul>${info.problems.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>`) : ''}</div>
    </div>
    <div class="unit"><span class="lbl">Models that write the units</span>
      <p class="hint">Several local models work on each unit at once on the worker nodes. The answer that passes with the fewest
        attempts is used, so the same answers always build the same file. Small models on the worker nodes take a few minutes
        a unit.</p>
      <div class="sy-inputs">${local.map(([id, name]) => `<label><input type="checkbox" data-buildby="${att(id)}"
        ${BUILD_BY.includes(id) ? 'checked' : ''}> ${esc(name)}</label>`).join('')}
        ${[['samples', 'Candidates per unit (1-25)'], ['retries', 'Repairs per candidate (1-5)'], ['rounds', 'Fresh rounds (1-20)']]
          .map(([k, label]) => `<label>${esc(label)}<input class="field" type="number" min="1" step="1" data-buildopt="${att(k)}"
            value="${att(String(BUILD_OPTS[k]))}" style="font-size:16px;max-width:8em;display:block"></label>`).join('')}</div>
      <label style="display:block;margin-top:12px">Keep the units an earlier build accepted
        <select class="field" id="syKeep" style="font-size:16px;display:block;max-width:100%">
          <option value="">None: ask the models for every unit</option>
          ${builds.map((r) => `<option value="${att(r.id)}" ${r.id === BUILD_KEEP ? 'selected' : ''}>${esc((r.title || r.id).slice(0, 90))} · ${esc(r.status || '')}</option>`).join('')}
        </select></label>
      <p class="hint">${BUILD_MODE === 'task-cards' ? 'An earlier task-card build is rechecked before reuse. Unchanged independent branches are kept; changed contracts and their consumers are rebuilt.' : 'After editing a unit that stalled, keep what already passed: the leading units that build accepted become fixed text, tested again, and only the rest are written.'}</p>
      <div class="sy-actions" style="margin-top:12px"><button class="btn" id="syBuild">Build</button></div>
    </div>
    <div class="unit"><details id="syDifferential"><summary>Compare candidate behavior</summary>
      <p class="hint">Paste complete JavaScript candidates for the sheet above. Each candidate is checked against every declared example before the same probe expressions are run locally. Differing results become questions for you to resolve in the specification.</p>
      <label style="display:block">Candidates (JSON array of label and source)
        <textarea class="field" id="syCandidates" rows="5" style="font-size:16px;width:100%;box-sizing:border-box"
          placeholder='[{"label":"first", "source":"function answer(){return 7;}"}]'></textarea></label>
      <label style="display:block;margin-top:10px">Probe expressions (JSON array)
        <textarea class="field" id="syProbes" rows="3" style="font-size:16px;width:100%;box-sizing:border-box"
          placeholder='["answer()"]'></textarea></label>
      <label style="display:block;margin-top:10px">Explicit external names (JSON array, when the sheet requires them)
        <input class="field" id="syCompareExternals" style="font-size:16px;width:100%;box-sizing:border-box"></label>
      <p class="hint">Up to 8 candidates and 64 probes; 30 seconds for the whole check. Candidate labels are supplied by you. Agreement covers these tests only. A differing result has no automatically chosen correct answer.</p>
      <button class="btn sm" id="syCompareCode" ${BUILD_COMPARING ? 'disabled' : ''}>${BUILD_COMPARING ? 'Checking candidates…' : 'Check and compare'}</button>
      <p id="syComparisonStatus" role="status"></p>
      <pre id="syComparisonResult" tabindex="0" aria-label="Differential comparison receipt" style="max-height:30em;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere"></pre>
    </details>
    </div>`;
    const box = $('sySheet');
    box.value = SHEET;
    box.oninput = () => { SHEET = box.value; SHEET_INFO = null; clearComparison(); try { localStorage.setItem(SHEET_KEY, SHEET); } catch (_) { } };
    function showComparison() {
      $('syComparisonResult').textContent = BUILD_COMPARISON ? JSON.stringify(BUILD_COMPARISON, null, 2) : '';
      $('syComparisonStatus').textContent = BUILD_COMPARISON
        ? 'Recorded comparison. Review proposed examples and choose their expected values before changing the sheet.' : '';
    }
    function clearComparison() { BUILD_COMPARISON = null; showComparison(); }
    $('syCandidates').value = BUILD_CANDIDATES;
    $('syProbes').value = BUILD_PROBES;
    $('syCompareExternals').value = BUILD_EXTERNALS;
    $('syCandidates').oninput = (e) => { BUILD_CANDIDATES = e.target.value; clearComparison(); };
    $('syProbes').oninput = (e) => { BUILD_PROBES = e.target.value; clearComparison(); };
    $('syCompareExternals').oninput = (e) => { BUILD_EXTERNALS = e.target.value; clearComparison(); };
    showComparison();
    if (BUILD_COMPARISON || BUILD_COMPARING) $('syDifferential').open = true;
    $('syCompareCode').onclick = async () => {
      if (BUILD_COMPARING) return;
      const sheet = SHEET, candidates = BUILD_CANDIDATES, probes = BUILD_PROBES, externals = BUILD_EXTERNALS;
      BUILD_COMPARING = true;
      $('syCompareCode').disabled = true;
      $('syComparisonStatus').textContent = 'Checking supplied code locally…';
      try {
        const result = await api(API + 'spec/compare', {sheet, candidates: JSON.parse(candidates), probes: JSON.parse(probes),
          externals: JSON.parse(externals)});
        if (sheet === SHEET && candidates === BUILD_CANDIDATES && probes === BUILD_PROBES && externals === BUILD_EXTERNALS) {
          BUILD_COMPARISON = result;
          if ($('syComparisonResult')) showComparison();
        } else if ($('syComparisonStatus')) $('syComparisonStatus').textContent = 'Inputs changed during the check. Compare the edited inputs again.';
      } catch (error) { if ($('syComparisonStatus')) $('syComparisonStatus').textContent = error.message; }
      finally {
        BUILD_COMPARING = false;
        if ($('syCompareCode')) { $('syCompareCode').disabled = false; $('syCompareCode').textContent = 'Check and compare'; }
      }
    };
    m.querySelectorAll('[data-buildby]').forEach((c) => { c.onchange = () => {
      BUILD_BY = Array.from(m.querySelectorAll('[data-buildby]')).filter((x) => x.checked).map((x) => x.dataset.buildby);
    }; });
    m.querySelectorAll('[data-buildopt]').forEach((f) => { f.onchange = () => { BUILD_OPTS[f.dataset.buildopt] = +f.value || 1; }; });
    $('syKeep').onchange = (e) => { BUILD_KEEP = e.target.value; if (BUILD_KEEP) { BUILD_MANIFEST = null; Studio.repaint(); } };
    $('syBuildMode').onchange = (e) => { BUILD_MODE = e.target.value; SHEET_INFO = null; BUILD_MANIFEST = null; Studio.repaint(); };
    if ($('syBuildBudget')) $('syBuildBudget').onchange = (e) => { BUILD_BUDGET = +e.target.value; };
    if ($('syBuildPresentation')) $('syBuildPresentation').onchange = (e) => { BUILD_PRESENTATION = e.target.value; };
    if ($('syBuildDeclarations')) $('syBuildDeclarations').oninput = (e) => { BUILD_DECLARATIONS = e.target.value; };
    if ($('syDeclarationTemplate')) $('syDeclarationTemplate').onclick = async () => {
      try {
        const checked = await api(API + 'spec/check', { sheet: SHEET, mode: 'task-cards' });
        if (!checked.ok || !checked.plan) throw new Error((checked.problems || ['Check the sheet first.']).join(' '));
        const contracts = Object.fromEntries(checked.plan.units.map(unit => [unit.id,
          {version: 1, exports: Object.fromEntries(unit.contract.unit.names.map(name => [name, 'function']))}]));
        BUILD_DECLARATIONS = JSON.stringify(contracts, null, 2);
        $('syBuildDeclarations').value = BUILD_DECLARATIONS; SHEET_INFO = checked;
      } catch (error) { toast(error.message); }
    };
    if ($('syClearManifest')) $('syClearManifest').onclick = () => { BUILD_MANIFEST = null; Studio.repaint(); };
    if ($('syBuildManifest')) $('syBuildManifest').onchange = async (e) => {
      const file = e.target.files[0]; if (!file) return;
      try {
        if (file.size > 4000000) throw new Error('The manifest exceeds 4 MB.');
        const manifest = JSON.parse(await file.text());
        await api(API + 'spec/verify', { manifest });
        BUILD_MANIFEST = manifest; BUILD_KEEP = ''; Studio.repaint();
      } catch (error) { toast(error.message); }
    };
    $('syExample').onclick = async () => {
      if (SHEET.trim() && !confirm('Replace the sheet with the Tetris example?')) return;
      try { SHEET = (await api(API + 'spec/example?name=tetris')).sheet; SHEET_INFO = null;
        try { localStorage.setItem(SHEET_KEY, SHEET); } catch (_) { } Studio.repaint(); } catch (e) { toast(e.message); }
    };
    $('syCheckSheet').onclick = async () => {
      try { SHEET_INFO = await api(API + 'spec/check', { sheet: SHEET, mode: BUILD_MODE,
        ...(BUILD_MODE === 'task-cards' ? {presentation: BUILD_PRESENTATION,
          declaration_contracts: BUILD_DECLARATIONS.trim() ? JSON.parse(BUILD_DECLARATIONS) : undefined} : {}) });
        Studio.repaint(); } catch (e) { toast(e.message); }
    };
    $('syBuild').onclick = async () => {
      if (!BUILD_BY.length) { toast('Tick at least one model.'); return; }
      try {
        const res = await api(API + 'spec/run', { sheet: SHEET, by: BUILD_BY, ...BUILD_OPTS, keep: BUILD_KEEP || undefined,
          mode: BUILD_MODE, budget: BUILD_BUDGET, manifest: BUILD_MANIFEST || undefined,
          ...(BUILD_MODE === 'task-cards' ? {presentation: BUILD_PRESENTATION,
            declaration_contracts: BUILD_DECLARATIONS.trim() ? JSON.parse(BUILD_DECLARATIONS) : undefined} : {}) });
        toast(res.kept ? `Building: ${res.kept} units kept, the rest checked one by one` : 'Building: every unit is checked before the next one starts');
        OPEN = null; OPEN_ID = res.id; await loadRuns(); Studio.go('runs');
      } catch (e) { toast(e.message); }
    };
  }

  // a long text output (a built file) is saved whole: the card shows the first 4000 characters only
  function saveName(label) { const s = String(label || '').trim(); return /^[\w.-]{1,80}\.[a-z0-9]{1,8}$/i.test(s) ? s : ''; }
  function saveButtons(m, outs) {
    m.querySelectorAll('[data-saveout]').forEach((b) => { b.onclick = () => {
      const o = outs[+b.dataset.saveout];
      const blob = new Blob([String(o.value)], { type: 'application/octet-stream' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = saveName(o.label) || 'output.txt';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }; });
  }

  function renderRuns(m) {
    if (!RUNS) { m.innerHTML = busy; loadRuns().then(() => Studio.repaint()); return; }
    if (OPEN_ID && (!OPEN || OPEN.id !== OPEN_ID)) { m.innerHTML = busy; loadRun(OPEN_ID).then(() => Studio.repaint()); return; }
    if (OPEN && OPEN.has_paper_map !== false && !(OPEN.id in PAPERMAP)) { m.innerHTML = busy; loadPaperMap(OPEN.id).then(() => Studio.repaint()); return; }
    if (OPEN) { renderRun(m, OPEN); return; }
    m.innerHTML = `<div class="unit"><span class="lbl">Runs</span>
      ${RUNS.length ? `<div class="rows">${RUNS.map((r) => `<div class="row tap" data-run="${att(r.id)}">
        <span class="dot ${running(r.status) ? 'on' : r.status === 'done' ? 'ok' : 'err'}"></span>
        <div class="grow"><div class="ttl">${esc(r.title || r.id)}</div><div class="sub">${esc([r.status, Array.isArray(r.by) ? r.by.join(' + ') : r.by, when(r.created), r.calls != null ? r.calls + ' calls' : ''].filter(Boolean).join(' · '))}</div></div>
        ${swatch(r.fingerprint)}</div>`).join('')}</div>` : '<div class="empty">No runs yet. Write a program and press Run.</div>'}</div>`;
    m.querySelectorAll('[data-run]').forEach((r) => { r.onclick = () => { OPEN_ID = r.dataset.run; OPEN = null; Studio.repaint(); }; });
  }

  window.SymblicOpenRun = function (id) {
    if (!/^[0-9a-f]{12}$/.test(String(id))) return;
    OPEN_ID = id; OPEN = null;
    Studio.go('runs');
  };

  function epistemicDetails(epistemic) {
    if (!epistemic || !Array.isArray(epistemic.claims)) return '';
    return `<div class="unit"><details class="sy-epistemic"><summary>Claim provenance · ${epistemic.claims.length} recorded claims</summary>
      <p class="hint">Type checks and derivations establish encoded properties. Owner premises, observations and model proposals retain their origins; empirical truth is not established by this record. Roots count distinct claims, not model calls; equal claims can share a root.</p><div data-claim-page></div></details></div>`;
  }

  function wireEpistemic(m, epistemic) {
    const details = m.querySelector('.sy-epistemic');
    if (!details) return;
    const claims = epistemic.claims;
    const views = new Map((epistemic.assessments || []).map(a => [a.id, a]));
    const mount = details.querySelector('[data-claim-page]');
    let page = 0, painted = false;
    const paint = () => {
      painted = true;
      const rows = claims.slice(page * 20, page * 20 + 20);
      mount.innerHTML = `<p class="hint">${claims.length ? page * 20 + 1 : 0}–${Math.min(claims.length, page * 20 + 20)} of ${claims.length}</p>` + rows.map((c, i) => {
        const a = views.get(c.id) || {}, roots = Array.isArray(a.conditional_on) ? a.conditional_on : [];
        const omitted = a.roots_omitted;
        const summarized = omitted && Number.isSafeInteger(omitted.count) && omitted.count >= 0 &&
          Number.isSafeInteger(omitted.total) && omitted.total === roots.length + omitted.count;
        const rootCount = summarized ? omitted.total : roots.length;
        const rootLabel = omitted && !summarized ? `${roots.length} listed root claim(s); total unavailable` : `${rootCount} root claim(s)`;
        return `<div class="card"><span class="lbl">${esc((c.content || {}).name || c.id)} · ${esc(c.origin)} · ${esc(a.status || c.status)}</span>
          <p class="hint">${esc(a.support || 'unassessed')} · ${esc(rootLabel)}${summarized && omitted.count ? ` · ${roots.length} listed, ${omitted.count} retained in summary` : ''}${a.lineage_complete === false ? ' · lineage summarized or incomplete' : ''}${a.admissible === false ? ' · unavailable to verified conclusions' : ''}</p>
          ${roots.length ? `<p class="hint">Listed root origins: ${esc([...new Set(roots.map(r => r.origin))].join(', '))}</p>` : ''}
          <details data-claim="${i}"><summary>Exact references and checks</summary><pre class="codeblock"></pre></details></div>`;
      }).join('') + `<div class="sy-acts"><button class="btn sm" data-claim-prev ${page ? '' : 'disabled'}>Previous claims</button><button class="btn sm" data-claim-next ${page * 20 + 20 < claims.length ? '' : 'disabled'}>Next claims</button></div>`;
      mount.querySelectorAll('[data-claim]').forEach(el => { el.ontoggle = () => {
        if (!el.open || el.querySelector('pre').textContent) return;
        const c = rows[+el.dataset.claim];
        el.querySelector('pre').textContent = JSON.stringify({ id:c.id, revision:c.revision, sha256:c.sha256,
          dependencies:c.dependencies, checks:c.checks, assessment:views.get(c.id) || {} }, null, 2);
      }; });
      mount.querySelector('[data-claim-prev]').onclick = () => { if (page) { page--; paint(); } };
      mount.querySelector('[data-claim-next]').onclick = () => { if (page * 20 + 20 < claims.length) { page++; paint(); } };
    };
    details.ontoggle = () => { if (details.open && !painted) paint(); };
  }

  function renderRun(m, v) {
    const st = v.state || {};
    const prog = st.progress || [0, 0];
    const outs = st.outputs || [];
    const draws = v.artifacts || [];
    const lockButton = v.status === 'done'
      ? '<button class="btn sm" id="syLock" title="Freeze this run into a lock: it replays with no model">Lock</button>'
      : '';
    m.innerHTML = `
      <div class="unit"><button class="btn sm ghost" id="syBack">← all runs</button></div>
      <div class="unit"><span class="lbl">${esc((v.meta && v.meta.title) || v.id)}</span>
        <div class="grid3">
          <div class="stat"><span class="lbl">status</span><div class="big ${v.status === 'done' ? '' : 'acc'}">${esc(v.status)}</div></div>
          <div class="stat"><span class="lbl">fingerprint</span><div class="big">${st.fingerprint ? swatch(st.fingerprint) : '—'}</div></div>
          <div class="stat"><span class="lbl">asks · calls · reused</span><div class="big">${+(st.asks || 0)} · ${+(st.calls || 0)} · ${+(st.cached || 0)}</div></div>
        </div>
        ${running(v.status) ? `<div class="meter" style="margin-top:12px"><div class="mrow"><span class="lbl">progress</span><span class="mval">${+prog[0]} / ${+prog[1]}</span></div><div class="well"><div class="fill" style="width:${prog[1] ? (100 * prog[0] / prog[1]).toFixed(0) : 0}%"></div></div></div>` : ''}
        ${st.error ? `<div class="card">${pill('bad', 'line ' + (st.error.line || 0))} ${esc(st.error.message || '')}</div>` : ''}
        <div class="sy-acts">
          ${running(v.status) ? '<button class="btn danger sm" id="syStop">Stop</button>' : '<button class="btn sm" id="syResume">Resume</button>'}
          <button class="btn sm" id="syLoad">Open program in editor</button>
          <a class="btn sm ghost" href="symblic.html?run=${att(v.id)}#runs">Link to saved run</a>
          ${v.status === 'done' && (v.source || '').includes('let spec_plan_json =') ? '<button class="btn sm" id="syExportManifest">Recheck and export build manifest</button>' : ''}
          ${lockButton}
          ${LOCKS[v.id] ? '<button class="btn sm" id="syReplay">Replay lock</button>' : ''}
          ${running(v.status) ? '' : '<button class="btn sm ghost" id="syDel">Delete</button>'}
        </div>
        ${LOCKS[v.id] ? `<div class="card"><span class="lbl">Lock</span><div class="hint">${esc(LOCKS[v.id].text)}</div></div>` : ''}
        <div class="hint">by ${esc(Array.isArray(v.meta && v.meta.by) ? v.meta.by.join(' + ') : (v.meta && v.meta.by) || 'the program\'s own use by=')} · ${esc(when(v.meta && v.meta.created))}${st.agreement != null ? ' · mean agreement ' + Math.round(100 * st.agreement) + '%' : ''}</div>
      </div>
      <div id="syDeterminism"></div>
      <div id="syCharacterFrames"></div>
      ${epistemicDetails(st.epistemic)}
      ${draws.length ? `<div class="unit"><span class="lbl">Drawings</span><div class="sy-draw">${draws.map((d) => `<figure><img alt="${att(d)}" data-art="${att(d)}"><figcaption>${esc(d)}</figcaption></figure>`).join('')}</div></div>` : ''}
      ${outs.length ? `<div class="unit"><span class="lbl">Outputs</span>${outs.map((o, i) => `<div class="card"><span class="lbl">${esc(o.kind)} · ${PAPERMAP[v.id] ? 'paper ' : ''}line ${+paperLine(PAPERMAP[v.id], o.line)} ${esc(o.label || '')}</span>${typeof o.value === 'string' && (o.value.length > 4000 || saveName(o.label)) ? `<button class="btn sm" data-saveout="${i}">Save ${esc(saveName(o.label) || 'output')} (${o.value.length} characters)</button>` : ''}<div style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(o.text || '')}</div>${swatch(o.hash)}</div>`).join('')}</div>` : ''}
      <div class="unit"><span class="lbl">Statements${PAPERMAP[v.id] ? ' · paper lines' : ''}</span><div class="sy-trace">${(v.trace || []).map((t) => traceRow(t, PAPERMAP[v.id])).join('') || '<div class="empty">Nothing yet.</div>'}</div></div>
      ${v.log ? `<div class="unit"><span class="lbl">Log</span><div class="codeblock sy-cap">${esc(v.log)}</div></div>` : ''}`;
    if (window.SymblicDeterminism) window.SymblicDeterminism.render($('syDeterminism'), st, {
      recheck: async () => (await api(API + 'run/recheck-models', { id: v.id })).model_identity,
    });
    if (window.SymblicFrames) window.SymblicFrames.mount($('syCharacterFrames'), outs);
    saveButtons(m, outs);
    if ($('syExportManifest')) $('syExportManifest').onclick = async (event) => {
      const button = event.currentTarget; button.disabled = true;
      try {
        const result = await api(API + 'spec/manifest', { id: v.id });
        const blob = new Blob([JSON.stringify(result.manifest, null, 2) + '\n'], { type: 'application/json' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = 'symblic-build-' + v.id + '.json'; document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        toast('Examples rechecked locally; exported exact code and dependency identities.');
      } catch (error) { toast(error.message); } finally { button.disabled = false; }
    };
    wireEpistemic(m, st.epistemic);
    $('syBack').onclick = () => { OPEN = null; OPEN_ID = ''; loadRuns().then(() => Studio.repaint()); };
    const act = async (route, msg) => { try { await api(API + route, { id: v.id }); toast(msg); await loadRun(v.id); Studio.repaint(); } catch (e) { toast(e.message); } };
    if ($('syStop')) $('syStop').onclick = () => act('stop', 'Stopping');
    if ($('syResume')) $('syResume').onclick = () => act('resume', 'Resumed: answers already given are reused');
    if ($('syLock')) $('syLock').onclick = async () => {
      try {
        const r = await api(API + 'lock', { id: v.id });
        LOCKS[v.id] = { text: `locked: ${r.statements} results, ${r.calls} answers, fingerprint ${r.fingerprint}` };
        Studio.repaint();
      } catch (e) { toast(e.message); }
    };
    if ($('syReplay')) $('syReplay').onclick = async () => {
      try {
        const r = await api(API + 'lock/replay', { id: v.id });
        LOCKS[v.id] = { text: r.ok ? `replayed with no model: fingerprint ${r.fingerprint} matches the lock (${r.cached} answers from it)`
          : `replay did not match: ${r.fingerprint} vs ${r.expected}${r.error ? ' · ' + r.error.message : ''}${(r.refused || []).length ? ' · ' + r.refused.length + ' call(s) not in the lock' : ''}` };
        Studio.repaint();
      } catch (e) { toast(e.message); }
    };
    if ($('syDel')) $('syDel').onclick = async () => {
      if (!confirm('Delete this run and its records?')) return;
      try { await api(API + 'delete', { id: v.id }); OPEN = null; OPEN_ID = ''; await loadRuns(); Studio.repaint(); } catch (e) { toast(e.message); }
    };
    $('syLoad').onclick = () => { if (!confirm('Replace the editor with this run\'s program?')) return; SRC = v.source || ''; INPUTS = Object.fromEntries(Object.entries((v.meta || {}).inputs || {}).map(([k, value]) => [k, JSON.stringify(value)])); TASK_SOURCE = SRC; TASK_OPTIONS = (v.meta || {}).options || {}; setStrictModelPins(STRICT_MODEL_PINS || TASK_OPTIONS.model_pins === 'strict'); CHECK = null; Studio.go('write'); };
    m.querySelectorAll('[data-art]').forEach((img) => {
      fetch(API + 'artifact?id=' + encodeURIComponent(v.id) + '&name=' + encodeURIComponent(img.dataset.art))
        .then((r) => r.ok ? r.text() : '').then((t) => { if (t) setSvg(img, t); });
    });
    m.querySelectorAll('[data-more]').forEach((b) => {
      b.onclick = () => { const s = b.parentElement.parentElement.querySelector('[data-samples]'); if (s) s.hidden = !s.hidden; };
    });
  }

  function paperLine(pmap, line) {
    return pmap && pmap.map && pmap.map[line - 1] ? pmap.map[line - 1].paper_line : line;
  }

  function traceRow(t, pmap) {
    const a = t.ask || null;
    const modulePremise = t.kind === 'module-knowledge';
    const pl = pmap && !modulePremise ? paperLine(pmap, t.line) : null;
    const lineTitle = modulePremise ? 'Module line ' + t.line + (t.note ? ' · ' + t.note : '')
      : pl ? 'program line ' + t.line : '';
    const acceptance = t.acceptance_lineage;
    const acceptedNames = acceptance && acceptance.scope === 'same_scope_values_selected_by_a_passed_check'
      && t.check && t.check.passed === true && typeof acceptance.check_id === 'string'
      && acceptance.check_id.length > 0 && acceptance.check_id === t.check.id
      && acceptance.bindings && typeof acceptance.bindings === 'object' && !Array.isArray(acceptance.bindings)
      ? Object.keys(acceptance.bindings) : [];
    const samples = a && a.samples ? a.samples : (a && a.items ? a.items.flatMap((it) => it.samples || []) : []);
    const agree = hasMeasuredAgreement(a) && typeof a.agreement === 'number' ? a.agreement : null;
    const evidence = (a && a.evidence) || t.evidence;
    const det = a && a.determination;
    const route = a && a.route === 'escalate';
    return `<div class="st"><div class="hd"><span class="ln" title="${att(lineTitle)}">L${+(pl || t.line)}</span><span class="nm">${esc(t.kind)}${t.name ? ' ' + esc(t.name) : ''}</span>
      ${t.class ? pill(t.class, t.class) : ''}${t.status && t.status !== 'ok' ? pill(t.status === 'contested' ? 'structured' : 'bad', t.status) : ''}
      ${agree != null && !route ? `<span class="sy-agree ${agree < 0.67 ? 'low' : ''}" title="${att('agreement ' + Math.round(agree * 100) + '%')}"><i style="width:${(agree * 100).toFixed(0)}%"></i></span><span class="hint">${Math.round(agree * 100)}%</span>` : ''}
      ${swatch(t.hash)}${samples.length ? `<button class="btn sm ghost" data-more="1">${samples.length} answers</button>` : ''}</div>
      ${t.value != null ? `<div class="vl">${esc(t.value)}</div>` : ''}${t.note ? `<div class="sm">${esc(t.note)}</div>` : ''}
      ${route && a.selected ? `<p class="hint">Checked answer from ${esc(a.selected)} · ${(a.route_attempts || []).length} model(s) tried</p>` : ''}
      ${t.check ? `<p class="hint">Encoded predicate ${t.check.passed ? 'passed' : 'failed'}: ${esc(t.check.predicate)}. This checks the written condition.</p>` : ''}
      ${acceptedNames.length ? `<p class="hint">Additional imported premises retained for: ${esc(acceptedNames.slice(0, 16).join(', '))}${acceptedNames.length > 16 ? ' and ' + (acceptedNames.length - 16) + ' more values' : ''}. Earlier evidence is preserved.</p>` : ''}
      ${det ? `<p class="hint">${esc(det.verdict)} in the declared domain · ${esc(det.accepted)} accepted of ${+det.domain} candidates${det.exhaustive ? ' · exhaustive' : ' · stopped after finding alternatives'}${det.witnesses ? '<br>Alternative values: ' + esc(JSON.stringify(det.witnesses)) : ''}</p>` : ''}
      ${evidence ? `<details class="hint sy-evidence"><summary>Verification and sources</summary>
        <p>${esc(assuranceLabel(evidence.assurance))}${evidence.mechanism ? ' · ' + esc(evidence.mechanism.replace(/_/g, ' ')) : ''}. Independence is not established.</p>
        ${(evidence.declared_modes || []).length ? '<p>Declared methods: ' + esc(evidence.declared_modes.join(', ')) + '</p>' : ''}
        ${(evidence.shared_dependencies || []).map((d) => '<div>Shared ' + esc(d.kind) + ': <span title="' + att(d.id) + '">' + esc(/^[a-f0-9]{64}$/.test(d.id) ? d.id.slice(0, 12) + '…' : d.id) + '</span> (' + d.observations.length + ' observations)</div>').join('')}
        ${(evidence.missing_provenance || []).length ? '<p>' + evidence.missing_provenance.length + ' observations have incomplete method/source declarations.</p>' : ''}
        ${(evidence.parents || []).length ? '<p>Derived from: ' + esc(evidence.parents.map((p) => p.name).join(', ')) + '. Input evidence is retained.</p>' : ''}
      </details>` : ''}
      ${samples.length ? `<div class="sm" data-samples hidden>${samples.map((s) => `<div>${s.ok ? swatch(s.hash) : pill('bad', 'invalid')} ${esc(s.app)}${s.node ? ' @' + esc(s.node) : ''} r${+s.round || 1}${s.cached ? ' · reused' : ''} · ${(+(s.ms || 0) / 1000).toFixed(1)}s · ${esc(s.ok ? (s.keyed ? s.value + ' ⇒ ' + s.keyed : s.value) : s.error)}</div>`).join('')}</div>` : ''}
    </div>`;
  }

  // ---------------------------------------------------------------- page: compare
  function renderCompare(m) {
    if (!CMPS) { m.innerHTML = busy; loadCmps().then(() => Studio.repaint()); return; }
    if (CMP_ID && (!CMP || CMP.id !== CMP_ID)) { m.innerHTML = busy; loadCmp(CMP_ID).then(() => Studio.repaint()); return; }
    if (CMP && !(CMP.id in PAPERVIEW)) { m.innerHTML = busy; loadPaperView(CMP.id).then(() => Studio.repaint()); return; }
    if (CMP) { renderMatrix(m, CMP); return; }
    m.innerHTML = `<div class="unit"><span class="lbl">Comparisons</span>
      <p class="hint">Start one from Write → Compare agents. Each runs the same program once per agent.</p>
      ${CMPS.length ? `<div class="rows">${CMPS.map((c) => `<div class="row tap" data-cmp="${att(c.id)}"><div class="grow"><div class="ttl">${esc(c.title || c.id)}</div><div class="sub">${esc(c.runs + ' agents · ' + when(c.created))}</div></div></div>`).join('')}</div>` : '<div class="empty">No comparisons yet.</div>'}</div>`;
    m.querySelectorAll('[data-cmp]').forEach((r) => { r.onclick = () => { CMP_ID = r.dataset.cmp; CMP = null; Studio.repaint(); }; });
  }

  function renderMatrix(m, c) {
    const s = c.summary || {};
    const cols = c.columns || [];
    // a paper's section prose is context the compiler adds (identical by construction): not a row here
    const keys = (s.statements || []).filter((x) => !(PAPERVIEW[c.id] && /:(section_\d+|paper_definitions)$/.test(x.key)));
    m.innerHTML = `
      <div class="unit"><button class="btn sm ghost" id="syBack2">← all comparisons</button></div>
      <div class="unit"><span class="lbl">${esc(c.title || c.id)}</span>
        <div class="grid3">
          <div class="stat"><span class="lbl">unanimous statements</span><div class="big">${+(s.unanimous || 0)} / ${+(s.total || 0)}</div></div>
          <div class="stat"><span class="lbl">pairwise identical</span><div class="big">${s.pairwise != null ? Math.round(100 * s.pairwise) + '%' : '—'}</div></div>
          <div class="stat"><span class="lbl">identical whole runs</span><div class="big ${s.identical_runs ? '' : 'acc'}">${+(s.same_runs || 0)} / ${+(s.runs || cols.length)}</div><div class="hint">${+(s.finished || 0)} finished</div></div>
        </div>
        <p class="hint" style="margin-top:8px">Agreement is not correctness: agents can agree on a wrong answer. Checks establish the encoded predicates; source accuracy, omitted requirements and premise truth need their own evidence.</p></div>
      ${paperViewHtml(PAPERVIEW[c.id])}
      <div class="unit"><div class="tblwrap"><table class="tbl sy-mx"><thead><tr><th>statement</th>${cols.map((col) => `<th>${esc(col.by)}<div class="hint">${esc(col.status)}${col.fingerprint ? ' · ' + esc(col.fingerprint.slice(0, 8)) : ''}</div></th>`).join('')}</tr></thead><tbody>
        ${keys.map((k) => {
          const hs = cols.map((col) => (col.rows[k.key] || {}).hash).filter(Boolean);
          const counts = {}; hs.forEach((h) => { counts[h] = (counts[h] || 0) + 1; });
          const modal = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
          return `<tr><td class="key">${esc(k.key)} ${k.class ? pill(k.class, k.class) : ''}<div class="hint">${Math.round(100 * k.agreement)}%</div></td>${cols.map((col) => {
            const cell = col.rows[k.key];
            if (!cell) return `<td class="hint">${esc(col.status === 'done' ? '—' : col.status)}</td>`;
            return `<td class="${cell.hash === modal ? 'same' : 'diff'}">${swatch(cell.hash)}<div>${esc(String(cell.value == null ? '' : cell.value).slice(0, 220))}</div></td>`;
          }).join('')}</tr>`;
        }).join('')}
      </tbody></table></div></div>
      <div class="unit">${cols.map((col) => `<button class="btn sm" data-open="${att(col.id)}">${esc(col.by)} run</button>`).join(' ')}</div>`;
    $('syBack2').onclick = () => { CMP = null; CMP_ID = ''; loadCmps().then(() => Studio.repaint()); };
    m.querySelectorAll('[data-open]').forEach((b) => { b.onclick = () => { OPEN_ID = b.dataset.open; OPEN = null; Studio.go('runs'); }; });
  }

  function paperViewHtml(pv) {
    if (!pv) return '';
    const u = pv.underspecified || [];
    const cov = pv.coverage || { finished: (pv.cohorts || []).length, of: (pv.cohorts || []).length, failed: [] };
    const verdict = pv.reproduces ? 'reproduces' : pv.results_reproduce ? 'its results reproduce; some readings differ' : 'does not reproduce';
    return `<div class="unit"><span class="lbl">The paper · ${esc(verdict)}</span>
      <p class="hint">${+pv.model_reproduced} of ${+pv.model_statements} model-dependent results are identical among the groups of agents that answered (${+cov.finished} of ${+cov.of} finished; each started from nothing). Differences can reflect ambiguous requirements, missing context or model errors; inspect those lines before proposing a rewrite.</p>
      ${(cov.failed || []).length ? `<p class="hint">Did not finish (not counted as disagreement): ${cov.failed.map((f) => esc(f.by) + ' (' + esc(String(f.error || f.status).slice(0, 90)) + ')').join('; ')}</p>` : ''}
      ${(pv.inherited || []).length ? `<p class="hint">${+pv.inherited.length} kernel result(s) differ only because of the lines below.</p>` : ''}
      ${u.length ? `<div class="rows">${u.map((x) => `<div class="row"><div class="grow"><div class="ttl">paper line ${+x.paper_line} · ${esc(x.section_title || '')}</div>
        <div class="sub mono">${esc(x.name)} · ${+x.distinct} different answers${(x.groups || []).length ? ' · ' + x.groups.map((g) => g[1].length + '× ' + String(g[0]).slice(0, 8)).join(', ') : ''}</div></div></div>`).join('')}</div>` : '<div class="hint">Every result is identical across the groups.</div>'}</div>`;
  }

  // ---------------------------------------------------------------- page: language
  function renderLanguage(m) {
    const b = (META && META.builtins) || {};
    m.innerHTML = `<div class="unit sy-ref">
      <p>Symblic composes explicit statements, model construction and scoped checks. Models can build answers, programs and proof terms; general checkers validate their encoded properties. The kernel also computes supported arithmetic, sets, finite logic and drawings. Choose <code>use profile=verified.</code> for explicit asks, strict coercion and guarded function purity. Existing programs retain the legacy profile. Checks remain conditional on their inputs and assumptions.</p>
      <h3>Statements</h3>
      <div class="codeblock">program Name.                     note free text.
given name: Type = default.       let name: Type = expression.
define Name as Type.              group panel = ["claude:haiku", "ollama:qwen3:4b-instruct@node-a"].
fact parent(ada, ben).            rule ancestor(X, Z) if parent(X, Y) and ancestor(Y, Z).
ask name: Type "instruction with {expressions}" from a, b with effort=high, votes=3, context=all
ensure condition else retry because "why".      assert condition.
if condition then … else … end.   for x in list do … end.   (names bound in a loop become lists)
show expression as "label".       draw flower(…) as "file.svg".
forget name.  pin name with weight=8.          delegate job = "task" to "triad".
Legacy profile only: plain sentences become implicit asks. Explicit/verified profiles reject them.</div>
      <h3>Building programs from parts</h3>
      <div class="codeblock">use profile=verified.
function area(side: Number) -> Number = side ^ 2.          (verified profile forbids routine/effect calls)
routine colour_of(thing: Text) -> one of {red, green} with effort=high do
  ask c: one of {red, green} "What colour is {thing}?"
  return c.
end.                               (a typed model function: same arguments, same answer within a run)
import units.   import stats as st.   import fleiss_kappa from stats.   import "Saved program" as p.
term cup means "the US legal cup, exactly 240 mL".   (every ask that uses the word is told the meaning)
test "a unit square" do assert area(1) = 1. end.     (Run tests in Write; skipped in a run)</div>
      <p>A <b>paper</b> (.symd) is Markdown: prose explains, <code>- **word**: meaning</code> defines, and <code>\`\`\`symblic</code> blocks are the statements. Compare agents on a paper to see whether groups of agents that knew nothing reproduce it, and which of its lines they read differently. A finished run can be <b>locked</b>: the lock replays it with no model at all. Details: docs/symblic/LANGUAGE-3.md.</p>
      <h3>Types (they become the answer's JSON Schema)</h3>
      <div class="codeblock">Int · Int in 1..10 · Number · Number to 2 places · Bool · Text · Text up to 60 words
one of {red, gold, pale-yellow} · List of T length 3..5 · Set of T · Record {name: Text, n: Int}
one of {fruit: "botanically, grown from the flower", vegetable: "any other edible part"}   (each option says what it means)</div>
      <h3>Per-statement controls</h3>
      <ul>
        <li><code>context=</code> <b>none</b> (default: a fresh context with only the <code>from</code> names), <b>all</b> (all of memory, highest weight first), <b>last 3</b>, <b>relevant</b> (deterministic word overlap), <b>facts</b>, or <code>[a, b]</code>. <code>budget=</code> bounds the system text, prompt and compact schema in Unicode characters, including repairs. Required named values must fit; optional omitted items are recorded. This is not a token limit.</li>
        <li><code>effort=</code> low (direct) · medium (reason, then answer) · high (3 votes) · max (5 votes) · ultra (5 votes, then every agent sees the anonymised answers once and answers again). Agent CLIs also get their own reasoning effort.</li>
        <li><code>votes=</code> how many answers; <code>ahead=2</code> stops as soon as one answer leads by two; <code>key=eval(it)</code> groups votes by meaning (two formulas with the same value agree; one the kernel cannot read is thrown out); <code>agree=0.8, strict</code> fails a contested statement.</li>
        <li><code>weight=</code> sets context priority. A high weight does not turn a proposal into an established fact; claim origins and dependency hashes travel with selected values.</li>
        <li><code>ambiguous=true</code> asks every agent to list the statement's other readings (kilometres or miles, a common or a leap year); they are recorded and shown as a warning. <code>ambiguous=fail</code> stops the run when any agent sees two readings. <code>solve</code> lets the kernel answer when its checks leave exactly one possible value.</li>
        <li><code>vote=</code> whole · fields (a record voted field by field; if the combined record fails a check, the most common whole record is used instead) · auto. <code>examples=[["q", answer]]</code> shows every agent the same worked examples.</li>
        <li><code>by=</code> an applicator: <code>claude:sonnet</code>, <code>codex</code>, <code>agy</code>, <code>ollama:qwen3:4b-instruct@node-b</code>, <code>gemini:pro</code>, <code>council:debate</code>, or a group.</li>
      </ul>
      <h3>Kernel</h3>
      <p>Numbers are exact rationals (0.1 + 0.2 = 0.3 exactly; 1/3 × 3 = 1). sqrt, sin, cos, exp and ln use Decimal arithmetic with defined precision and rounding. Lists index from 1. Unicode logic works: <code>∀ x ∈ xs: x ≥ 0</code>, <code>a ∧ ¬b → c</code>.</p>
      <div class="codeblock">${Object.entries(b).map(([k, v]) => esc(k.padEnd(12) + ' ' + v)).join('\n')}</div>
      <h3>What is guaranteed, and what is measured</h3>
      <ul>
        <li><b>Kernel checks:</b> formal computations have defined rules and canonical fingerprints. Compare results under the same kernel identity, which includes numeric and Unicode dependencies. Cross-machine conformance is tested on a finite corpus; replay requires its recorded dependencies and answers.</li>
        <li><b>Measured, not guaranteed:</b> whether different agents give the same answer to an ask. A closed type limits possible outputs but does not establish accuracy or fresh-run determinism. Repeated agreement must be measured for the actual task and model.</li>
        <li><b>Identical by construction for checked asks:</b> when an ask's checks admit exactly one answer, every answer the kernel accepts is that answer, whoever gave it; what is measured is who reaches it.</li>
        <li><b>Tighten</b> proposes rewrites, retains original requirements and records adoption separately. Independent held-out requirements/examples test fidelity; a different panel alone cannot establish preserved intent.</li>
        <li><b>Checks:</b> ensure/assert enforce their encoded predicates. A passing check alone does not establish factual truth or that the predicate captures the author's intention.</li>
      </ul>
      <p class="hint">Prior work and how Symblic relates to it: docs/symblic/PRIOR-ART.md. Specification: docs/symblic/SPEC.md.</p>
    </div>
    <div class="unit" id="syLib"></div>
    <div class="unit" id="syJobs"></div>`;
    paintLibrary();
    paintJobs();
  }

  async function loadJobs() { try { LJOBS = (await api(API + 'lang/jobs')).jobs; } catch (e) { LJOBS = { error: e.message }; } }

  function jobDetailHtml(v) {
    if (!v) return busy;
    if (v.error) return `<div class="empty">${esc(v.error)}</div>`;
    const r = (v.result || {}).result || {};
    if (v.result && v.result.status === 'failed') return `<div class="card">${pill('bad', 'failed')} ${esc(v.result.error || '')}</div>`;
    if (v.job.kind === 'certify' && r.tests) {
      const cohorts = (r.cohorts || []).map((c) => c.by);
      return `<div class="tblwrap"><table class="tbl"><thead><tr><th>test</th>${cohorts.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>
        ${r.tests.map((t) => `<tr><td>${esc(t.title)}</td>${t.cohorts.map((c) => `<td>${pill(c.status === 'passed' ? 'good' : 'bad', c.status)}${c.error ? `<div class="hint">${esc(c.error)}</div>` : ''}</td>`).join('')}</tr>`).join('')}
      </tbody></table></div><p class="hint">${(r.certified || []).length} of ${(r.tests || []).length} tests pass for every agent: a routine is certified for these agents when all of its tests do. Passing is decided by the tests' own assertions, never by agreement.</p>`;
    }
    if (v.job.kind === 'crystallise' && r.module) {
      const nk = (r.kept || []).length;
      return `<p class="hint">${nk} ${nk === 1 ? 'answer' : 'answers'} kept, ${(r.left_out || []).length} left out. Answered by ${esc((r.applicators || []).join(', '))} (${esc((r.families || []).join(', '))}).</p>
        ${(r.left_out || []).length ? `<div class="rows">${r.left_out.map((x) => `<div class="row"><div class="grow"><div class="ttl mono">${esc(JSON.stringify(x.input))}</div><div class="sub">${esc(x.reason)}</div></div></div>`).join('')}</div>` : ''}
        <div class="codeblock sy-cap">${esc(r.module)}</div>
        <div class="sy-acts"><button class="btn sm" data-jsave="${att(v.id)}">Save as program…</button></div>`;
    }
    return `<div class="hint">${esc(v.status)}</div>${v.log ? `<div class="codeblock sy-cap">${esc(v.log.slice(-1500))}</div>` : ''}`;
  }

  function paintJobs() {
    const el = $('syJobs');
    if (!el) return;
    if (!LJOBS) { el.innerHTML = busy; loadJobs().then(paintJobs); return; }
    if (LJOBS.error) { el.innerHTML = `<div class="empty">${esc(LJOBS.error)}</div>`; return; }
    el.innerHTML = `<span class="lbl">Jobs · certify and crystallise</span>
      ${LJOBS.length ? LJOBS.map((j) => `<details class="card" data-job="${att(j.id)}" ${LJOB[j.id] ? 'open' : ''}><summary><span class="dot ${running(j.status) ? 'on' : j.status === 'done' ? 'ok' : 'err'}"></span> ${esc(j.title || j.kind)} <span class="hint">${esc([j.status, j.summary, when(j.created)].filter(Boolean).join(' · '))}</span></summary>
        ${running(j.status) ? `<div class="sy-acts"><button class="btn sm danger" data-jstop="${att(j.id)}">Stop</button></div>` : ''}
        <div data-jd>${LJOB[j.id] ? jobDetailHtml(LJOB[j.id]) : ''}</div></details>`).join('') : '<div class="empty">No jobs yet. Certify a library module above, or Crystallise… a routine from Write.</div>'}`;
    el.querySelectorAll('details[data-job]').forEach((d) => {
      d.addEventListener('toggle', async () => {
        const id = d.dataset.job;
        if (!d.open) { delete LJOB[id]; return; }
        try { LJOB[id] = await api(API + 'lang/job?id=' + encodeURIComponent(id)); } catch (e) { LJOB[id] = { error: e.message }; }
        d.querySelector('[data-jd]').innerHTML = jobDetailHtml(LJOB[id]);
        wireJobButtons(d);
      });
      wireJobButtons(d);
    });
    el.querySelectorAll('[data-jstop]').forEach((b) => {
      b.onclick = async () => { try { await api(API + 'lang/stop', { id: b.dataset.jstop }); toast('Stopping'); await loadJobs(); paintJobs(); } catch (e) { toast(e.message); } };
    });
  }

  function wireJobButtons(root) {
    root.querySelectorAll('[data-jsave]').forEach((b) => {
      b.onclick = async () => {
        const name = prompt('Save the crystal as a program (then: import "name")', '');
        if (!name) return;
        try { await api(API + 'lang/save', { id: b.dataset.jsave, name }); toast('Saved'); await loadPrograms(); } catch (e) { toast(e.message); }
      };
    });
  }

  function paintLibrary() {
    const el = $('syLib');
    if (!el) return;
    if (!LIB) { el.innerHTML = busy; loadLibrary().then(paintLibrary); return; }
    if (LIB.error) { el.innerHTML = `<div class="empty">${esc(LIB.error)}</div>`; return; }
    el.innerHTML = `<span class="lbl">Standard library · import NAME</span>
      ${LIB.map((mod) => `<details class="card"><summary><b class="mono">${esc(mod.name)}</b> · ${esc(mod.title)} <span class="hint">${+mod.items.length} names · ${+mod.tests.length} tests</span></summary>
        <p class="hint">${esc(mod.intro || '')}</p>
        <div class="rows">${mod.items.map((it) => `<div class="row"><div class="grow"><div class="ttl mono">${esc(it.signature)}</div>${it.doc ? `<div class="sub">${esc(it.doc)}</div>` : ''}</div>${it.asks ? pill('closed', it.asks + (it.asks === 1 ? ' ask' : ' asks')) : ''}</div>`).join('')}</div>
        <div class="sy-acts"><button class="btn sm" data-libtest="${att(mod.name)}">Run its tests</button>${mod.tests.length ? `<button class="btn sm" data-libcert="${att(mod.name)}" title="Run its tests once per agent you pick, each from nothing">Certify with agents…</button>` : ''}<button class="btn sm ghost" data-libopen="${att(mod.name)}">Open in editor</button></div>
        ${LIBTESTS[mod.name] ? `<div style="margin-top:8px">${LIBTESTS[mod.name].error ? `<div class="empty">${esc(LIBTESTS[mod.name].error)}</div>` : testsHtml(LIBTESTS[mod.name])}</div>` : ''}
      </details>`).join('')}`;
    el.querySelectorAll('[data-libtest]').forEach((b) => {
      b.onclick = async () => {
        const name = b.dataset.libtest;
        try {
          const mod = await api(API + 'module?name=' + encodeURIComponent(name));
          LIBTESTS[name] = await api(API + 'tests', { source: mod.source });
        } catch (e) { LIBTESTS[name] = { error: e.message }; }
        paintLibrary();
        const d = el.querySelector(`[data-libtest="${CSS.escape(name)}"]`);
        if (d) d.closest('details').open = true;
      };
    });
    el.querySelectorAll('[data-libcert]').forEach((b) => {
      b.onclick = () => agentSheet('Certify ' + b.dataset.libcert + ' with agents',
        'Each agent you tick runs the module\'s tests once, from nothing. A test certified for these agents passes for every one of them. Runs on the worker nodes.',
        ['claude:haiku', 'codex'], '',
        async (sheet, agents) => {
          if (!agents.length) { toast('Tick at least one'); return false; }
          await api(API + 'lang/certify', { module: b.dataset.libcert, cohorts: agents });
          toast('Certifying: see Jobs below');
          await loadJobs(); paintJobs();
        });
    });
    el.querySelectorAll('[data-libopen]').forEach((b) => {
      b.onclick = async () => {
        if (SRC.trim() && !confirm('Replace the editor with this module?')) return;
        try { SRC = (await api(API + 'module?name=' + encodeURIComponent(b.dataset.libopen))).source; saveDraft(); CHECK = null; Studio.go('write'); }
        catch (e) { toast(e.message); }
      };
    });
  }

  // ---------------------------------------------------------------- page: evidence
  function md(text) {
    // a deliberately small markdown renderer for the bench report: headings, lists, tables, paragraphs
    const lines = String(text || '').split('\n');
    let html = '', i = 0;
    const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');
    while (i < lines.length) {
      const l = lines[i];
      if (/^#{1,3} /.test(l)) { html += `<h2>${inline(l.replace(/^#+ /, ''))}</h2>`; i++; continue; }
      if (/^\|/.test(l)) {
        const rows = [];
        while (i < lines.length && /^\|/.test(lines[i])) { rows.push(lines[i]); i++; }
        const cells = (r) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
        html += '<div class="tblwrap" tabindex="0" role="region" aria-label="Evidence table"><table><thead><tr>' + cells(rows[0]).map((c) => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
          + rows.slice(2).map((r) => '<tr>' + cells(r).map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table></div>';
        continue;
      }
      if (/^- /.test(l)) {
        html += '<ul>';
        while (i < lines.length && /^- /.test(lines[i])) { html += `<li>${inline(lines[i].slice(2))}</li>`; i++; }
        html += '</ul>';
        continue;
      }
      if (l.trim()) html += `<p>${inline(l)}</p>`;
      i++;
    }
    return html;
  }

  function renderEvidence(m) {
    if (!EVID) { m.innerHTML = busy; loadEvidence().then(() => Studio.repaint()); return; }
    if (EVID.error) { m.innerHTML = `<div class="unit"><div class="empty">${esc(EVID.error)}</div></div>`; return; }
    const ki = EVID.kernel || [];
    const matchedScope = (bch) => {
      const runner = bch.summary && bch.summary.runner;
      if (!runner) return '<p class="hint">Endpoint and implementation-version metadata were not recorded for this evaluation.</p>';
      const scope = runner.endpoint === 'one_exact_typed_decision'
        ? 'Scope: one typed decision per task. These results do not establish whole-project reliability.'
        : 'Evaluation endpoint: ' + String(runner.endpoint || 'not recorded') + '. Inspect the declared scope before comparing results.';
      return '<p class="hint">' + esc(scope) + '</p>' + (runner.current_implementation_matches === false
        ? '<p class="hint">' + pill('bad', 'Historical implementation') + ' Recorded implementation differs from current code. These results describe the recorded version.</p>'
        : runner.current_implementation_matches === true ? ''
        : '<p class="hint">Compatibility with the current implementation was not established.</p>');
    };
    m.innerHTML = `
      <div class="unit"><span class="lbl">Kernel identity across machines</span>
        <p class="hint">The same kernel programs run on every node of the cluster: different CPUs, operating systems and Python versions. Identical fingerprints mean identical results, byte for byte.</p>
        ${ki.length ? `<div class="tblwrap"><table class="tbl"><thead><tr><th>machine</th><th>python</th><th>arch</th><th>program</th><th>fingerprint</th></tr></thead><tbody>
          ${ki.map((r) => `<tr><td class="mono">${esc(r.node)}</td><td class="num">${esc(r.python)}</td><td class="mono">${esc(r.machine)}</td><td class="mono">${esc(r.program)}</td><td>${swatch(r.fingerprint)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No cross-machine record yet.</div>'}
      </div>
      <div class="unit" id="syLangEv"></div>
      ${(EVID.matched || []).map(bch => `<div class="unit sy-md"><span class="lbl">Matched evaluation ${esc(bch.name)}</span>
        ${bch.ok ? matchedScope(bch) + md(bch.markdown) : `<p class="hint">${esc(bch.error || 'The evidence record could not be validated.')}</p>`}</div>`).join('')}
      ${(EVID.benches || []).map((bch) => `<div class="unit sy-md"><span class="lbl">Benchmark ${esc(bch.name)} · ${+bch.cells} cells${bch.running ? ' · still running' : ''}</span>${md(bch.report)}</div>`).join('') || '<div class="unit"><div class="empty">No benchmark yet.</div></div>'}`;
    paintLangEvidence();
  }

  // The abstraction layer's experiments (papers reproduced by fresh groups of agents, modules certified,
  // routines crystallised): GET lang/evidence.
  let LANGEV = null;
  async function paintLangEvidence() {
    const el = $('syLangEv');
    if (!el) return;
    if (!LANGEV) {
      el.innerHTML = busy;
      try { LANGEV = (await api(API + 'lang/evidence')).experiments; } catch (e) { LANGEV = { error: e.message }; }
      if (!$('syLangEv')) return;
    }
    if (LANGEV.error) { el.innerHTML = `<div class="empty">${esc(LANGEV.error)}</div>`; return; }
    const verdict = (e) => e.reproduces ? pill('good', 'reproduces') : e.results_reproduce ? pill('structured', 'results reproduce') : pill('bad', 'does not reproduce');
    const mark = (c) => c.correct === true ? ' ✓' : c.correct === false ? ' ✗' : '';
    el.innerHTML = `<span class="lbl">Papers, certifications and crystals</span>
      <p class="hint">Each paper ran once per group of agents, every group starting from nothing. Same colour = identical run. ✓/✗ = right or wrong against an exact expected result; an agent that did not finish (an outage) is not counted as disagreeing. Agreement is not correctness.</p>
      ${(LANGEV || []).map((e) => {
        if (e.kind === 'reproduce') return `<div class="card"><div class="ttl">${esc(e.title || e.name)} ${verdict(e)}</div>
          <div class="hint">${+e.finished} of ${+e.of} groups finished · ${e.model_reproduced != null ? +e.model_reproduced + '/' + (+e.model_statements) + ' model results identical' : ''} · ${esc(e.name)}</div>
          <div class="sy-acts">${e.cohorts.map((c) => `<span class="sy-pill">${esc(c.by)}${c.status === 'done' ? '' : ' · ' + esc(c.status)}${mark(c)}</span>${c.fingerprint && c.status === 'done' ? swatch(c.fingerprint) : ''}`).join(' ')}</div>
          ${e.underspecified.length ? `<div class="hint">Read differently: ${e.underspecified.map((u) => 'paper line ' + (+u.paper_line) + ' (' + esc(u.section || '') + ', ' + esc(u.name) + ': ' + (+u.distinct) + ' readings)').join('; ')}</div>` : ''}</div>`;
        if (e.kind === 'certify') return `<div class="card"><div class="ttl">Certification · ${esc(e.name)}</div>
          <div class="hint">${e.tests.map((t) => esc(t.title) + ' ' + (+t.passed) + '/' + (+t.of) + (+t.inconclusive ? ' · ' + (+t.inconclusive) + ' inconclusive' : '')).join(' · ')}</div></div>`;
        if (e.kind === 'crystallise') return `<div class="card"><div class="ttl">Crystal ${esc(e.routine || '')}</div>
          <div class="hint">${+e.kept} kept, ${+e.left_out} left out · answered by ${esc((e.applicators || []).join(', '))} (${esc((e.families || []).join(', '))})</div></div>`;
        return '';
      }).join('') || '<div class="empty">No experiments yet.</div>'}`;
  }

  // ---------------------------------------------------------------- polling
  function poll() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      try {
        if (!document.hidden) {
          if (Studio.page === 'runs') {
            if (OPEN && running(OPEN.status)) { await loadRun(OPEN.id); Studio.repaint(); }
            else if (!OPEN && RUNS && RUNS.some((r) => running(r.status))) { await loadRuns(); Studio.repaint(); }
          } else if (Studio.page === 'compare' && CMP && (CMP.columns || []).some((c) => running(c.status))) {
            await loadCmp(CMP.id); Studio.repaint();
          } else if (Studio.page === 'tighten' && TJOB && TJOB.status === 'running') {
            await loadTighten(TJOB.id); Studio.repaint();
          } else if (Studio.page === 'language' && Array.isArray(LJOBS) && LJOBS.some((j) => running(j.status))) {
            await loadJobs();
            for (const id of Object.keys(LJOB)) { try { LJOB[id] = await api(API + 'lang/job?id=' + encodeURIComponent(id)); } catch (_) { } }
            paintJobs();
          }
        }
      } finally { poll(); }
    }, 3500);
  }

  function renderAcademy(m) {
    m.innerHTML = `
      <div class="unit">
        <span class="lbl">Learning Suite</span>
        <h2>Symblic Academy & Mastery Platform</h2>
        <p class="hint">Practise Symblic construction and checking: explicit statements, kernel predicates, model proposals, evidence limits, flashcards, cloze exercises, syntax drills, quizzes, and guided projects. Study progress records practice, not certification.</p>
        <div style="display:flex; gap:12px; margin:16px 0; flex-wrap:wrap;">
          <a class="btn primary" href="symblic-guides/index.html" style="text-decoration:none; display:inline-flex; align-items:center; gap:6px;">
            <span>Open the guides</span>
          </a>
          <span class="hint">The original host also served a separate Academy page (flashcards, cloze blanks, syntax drills, capstone projects); it is not part of this repository.</span>
        </div>
        <div class="card" style="margin-top:16px; padding:16px; border:1px solid var(--brd); border-radius:4px; background:var(--bg1);">
          <h3>Curriculum Highlights</h3>
          <ul style="padding-left:20px; line-height:1.7; margin-top:8px;">
            <li><strong>Construction and Checking:</strong> Models or humans propose answers, programs and proof terms; supported checkers validate declared conditions. Exact arithmetic remains available.</li>
            <li><strong>Explicit Context:</strong> Select inputs, definitions and evidence dependencies. Missing referents and malicious source text remain concerns; a small capsule is not an immunity guarantee.</li>
            <li><strong>Transactional Retry:</strong> Restore internal state at anchor asks and supply bounded feedback. External actions follow separate effect recovery rules.</li>
            <li><strong>Datalog & Finite Geometry:</strong> Derive consequences of supplied facts and check explicit polyhedra. A valid calculation does not establish the accuracy of its inputs.</li>
            <li><strong>Epistemic Foundations:</strong> Distinguish evidence from agreement, finite mathematical adapters from semantic claims, and research proposals from tested capabilities.</li>
          </ul>
        </div>
      </div>
    `;
  }

  function disposeWriteDiagnostics() {
    clearTimeout(checkTimer); checkSeq++; writeDiagnostics?.destroy(); writeDiagnostics = null;
  }
  window.addEventListener('hashchange', () => {
    if (location.hash.split('?')[0] !== '#write' && location.hash) disposeWriteDiagnostics();
  });

  function focusedNavigation() {
    document.body.classList.add('sy-focused');
    const nav = document.createElement('nav'); nav.className = 'sy-quick-nav'; nav.setAttribute('aria-label', 'Symblic main views');
    for (const [id, name] of [['english', 'English'], ['write', 'Native'], ['runs', 'Runs']]) {
      const link = document.createElement('a'); link.href = '#' + id; link.textContent = name; link.dataset.syPage = id;
      nav.append(link);
    }
    $('barAux').append(nav);
    $('hamBtn').setAttribute('aria-label', 'All Symblic tools');
    updateFocusedNavigation();
  }
  function updateFocusedNavigation() {
    document.body.dataset.syPage = Studio.page;
    document.querySelectorAll('.sy-quick-nav [data-sy-page]').forEach(link => {
      if (link.dataset.syPage === Studio.page) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }
  function toolSearch(mount) {
    mount.innerHTML = '<label class="lbl" for="syToolSearch">Find a tool</label><input class="field" id="syToolSearch" type="search" placeholder="Build, workcards, evidence…"><p class="hint sy-tool-links"><a href="index.html">Automation canvas</a> · <a href="symblic-guides/index.html">Guides</a></p><p id="syToolCount" class="hint" role="status"></p>';
    $('syToolSearch').addEventListener('input', event => {
      const value = event.target.value.trim().toLocaleLowerCase(); let count = 0;
      document.querySelectorAll('#menuBody .mi').forEach(item => {
        item.hidden = !item.textContent.toLocaleLowerCase().includes(value); if (!item.hidden) count++;
      });
      document.querySelectorAll('#menuBody .grp').forEach(group => { group.hidden = !group.querySelector('.mi:not([hidden])'); });
      $('syToolCount').textContent = value ? `${count} matching tools` : '';
    });
  }

  // Explicit saved-run and tool links keep their routes; a new visit starts in English.
  if (!location.hash) history.replaceState(null, '', location.pathname + location.search + (linkedRun ? '#runs' : '#english'));

  Studio.boot({
    title: 'Symblic',
    wide: true,
    pages: [
      { id: 'write', ix: '01', name: 'Write', sub: 'program, check, preview, run', grp: 'Symblic', render: renderWrite },
      { id: 'english', ix: '01b', name: 'English', sub: 'one instruction, one fresh worker, checked progress', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicEnglish) window.SymblicEnglish.render(mount);
          else mount.textContent = 'English statements need the page update. Reload to try again.';
        } },
      { id: 'inquiry', ix: '01c', name: 'Inquiry', sub: 'choose the next evidence method', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicInquiry) window.SymblicInquiry.render(mount);
          else mount.textContent = 'Inquiry planning needs the page update. Reload to try again.';
        } },
      { id: 'experiments', ix: '01d', name: 'Experiments', sub: 'run and compare mathematical mechanisms', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicExperiments) window.SymblicExperiments.render(mount);
          else mount.textContent = 'Experiments need the page update. Reload to try again.';
        } },
      { id: 'interpreter', ix: '02', name: 'Interpreter', sub: 'describe, clarify, translate, run', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicIntent) window.SymblicIntent.render(mount);
          else mount.textContent = 'The Interpreter interface is unavailable. Reload this page to try again.';
        } },
      { id: 'logic', ix: '02b', name: 'Logic', sub: 'human premises → model proof → checked derivation', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicLogic) window.SymblicLogic.render(mount, { currentBy: () => BY, open: (task) => {
            SRC = task.source; INPUTS = Object.fromEntries(Object.entries(task.inputs).map(([key, value]) =>
              [key, JSON.stringify(value)])); TASK_OPTIONS = task.options || {}; TASK_SOURCE = task.source;
            if (typeof task.by === 'string' && task.by) setBy(task.by);
            saveDraft(); CHECK = null; Studio.go('write');
          } });
          else mount.textContent = 'The Logic interface is unavailable. Reload this page to try again.';
        } },
      { id: 'supervisor', ix: '02e', name: 'Supervisor', sub: 'durable native runs, waits, joins and clocks', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicSupervisor) window.SymblicSupervisor.render(mount);
          else mount.textContent = 'Supervisor needs the page update. Reload to try again.';
        } },
      { id: 'workcards', ix: '02f', name: 'Workcards', sub: 'small checked steps, builder and critic', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicWorkcards) window.SymblicWorkcards.render(mount, { currentBy: () => BY, open: (task) => {
            SRC = task.source; INPUTS = Object.fromEntries(Object.entries(task.inputs).map(([key, value]) => [key, JSON.stringify(value)]));
            TASK_OPTIONS = task.options || {}; TASK_SOURCE = task.source;
            saveDraft(); CHECK = null; Studio.go('write');
          } });
          else mount.textContent = 'The Workcards interface is unavailable. Reload this page to try again.';
        } },
      { id: 'graphs', ix: '02c', name: 'Graphs', sub: 'bounded steps, explicit edges, saved receipts', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicGraphs) window.SymblicGraphs.render(mount);
          else mount.textContent = 'The Graphs interface is unavailable. Reload this page to try again.';
        } },
      { id: 'policies', ix: '02d', name: 'Policies', sub: 'frozen routing candidates and held-out comparison', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicPolicies) window.SymblicPolicies.render(mount);
          else mount.textContent = 'The Policies interface is unavailable. Reload this page to try again.';
        } },
      { id: 'memory', ix: '02e', name: 'Memory', sub: 'premises, revisions, disagreements and context', grp: 'Symblic',
        render: (mount) => {
          if (window.SymblicMemory) window.SymblicMemory.render(mount);
          else mount.textContent = 'The notebook interface is unavailable. Reload this page to try again.';
        } },
      { id: 'plan', ix: '03', name: 'Plan', sub: 'every statement and how it is decided', grp: 'Symblic', render: renderPlan },
      { id: 'runs', ix: '04', name: 'Runs', sub: 'traces, votes, fingerprints, drawings', grp: 'Symblic', render: renderRuns },
      { id: 'compare', ix: '05', name: 'Compare', sub: 'one program, many agents', grp: 'Symblic', render: renderCompare },
      { id: 'tighten', ix: '06', name: 'Tighten', sub: 'find and fix what agents read differently', grp: 'Symblic', render: renderTighten },
      { id: 'build', ix: '07', name: 'Build', sub: 'spec sheet → local models → a tested file', grp: 'Symblic', render: renderBuild },
      { id: 'language', ix: '08', name: 'Language', sub: 'statements, types, controls, kernel', grp: 'Learn', render: renderLanguage },
      { id: 'evidence', ix: '09', name: 'Evidence', sub: 'what has been measured', grp: 'Learn', render: renderEvidence },
      { id: 'academy', ix: '10', name: 'Academy', sub: 'tutorials, flashcards, drills & projects', grp: 'Learn', render: renderAcademy },
    ],
    menuSub(id) {
      if (id === 'runs' && RUNS) { const n = RUNS.filter((r) => running(r.status)).length; return n ? n + ' running' : null; }
      if (id === 'write' && CHECK) return CHECK.ok ? (CHECK.plan || []).length + ' statements' : (CHECK.errors || []).length + ' error(s)';
      return null;
    },
    menuNow(el) {
      toolSearch(el);
    },
    onPage(id) {
      updateFocusedNavigation();
      if (id !== 'write') disposeWriteDiagnostics();
      if (id !== 'english') window.SymblicEnglish?.disposeDiagnostics?.();
    },
    onBoot() { focusedNavigation(); loadMeta().then(() => { if (Studio.page === 'write') Studio.repaint(); }); loadPrograms(); loadRuns(); poll(); },
    footLinks: '<a class="btn sm ghost" href="../hub/index.html">Symblic</a><a class="btn sm ghost" href="symblic-guides/index.html">Guides</a>',
  });
})();
