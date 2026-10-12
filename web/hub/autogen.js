/* Autogen: explicit dispatch only. Observation, polling and reconnect never start or resume work. */
(() => {
  'use strict';
  const API = '/api/symblicos/';
  const SAVED = 'symblic.autogen.selection.v1';
  const RUN_ID = /^autogen-[a-f0-9]{24}$/;
  const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'unknown']);
  // stuck (until_done): nothing drives the run until the owner changes something and resumes it. It is not
  // polled, and unlike the ended statuses it can still be resumed or cancelled.
  const STUCK_HINT = 'Resume after changing the statement, the checks or the catalogue';
  const POLL_MS = 10000;
  const INTS = [['candidates', 'Candidates per statement'], ['regenerate', 'Regenerations after the first wave'],
    ['depth', 'Split depth'], ['children', 'Statements per split'], ['generations', 'Handoff or perpetual generations'],
    ['agents_max', 'Agents for the whole run']];
  const TIMES = [['attempt_seconds', 'Minutes per attempt', 60], ['wall_seconds', 'Hours for the whole run', 3600],
    ['interval_seconds', 'Minutes between perpetual generations', 60]];
  const STRATEGY_TITLES = {fresh: 'Fresh agent', feedback: 'Feedback from public checks', other_node: 'Another machine',
    other_engine: 'Another agent type'};  // stronger_model is refused by the server until a model ladder exists
  // Autogen v2 fields: offered and sent only when the catalogue lists them, because an older server refuses unknown fields.
  const V2_INTS = [['novelty_limit', 'Attempts without progress before a split'],
    ['saturation', 'Perpetual generations with nothing new before the lane stops', '0 = never; perpetual lanes only']];
  const V2_FLAGS = [
    ['until_done', 'Until done (no clock or count caps; agents keep regenerating, subdividing and re-planning until the checks pass or the statement is stuck)'],
    ['designer', 'Test designer (an independent agent writes AUTOGEN-TESTS.sh first; it must fail on an empty folder)'],
    ['self_split', 'Self-split (a worker may answer too big with a split file)']];
  const UNLIMITED = ['agents_max', 'wall_seconds'];          // until_done: blank or 0 = unlimited, a value is a safety cap
  const NOT_CAPS = ['regenerate', 'depth', 'generations'];   // with until_done these no longer end a statement
  const KIND_LABELS = new Map([['designer', 'test designer'], ['integration', 'integration check']]);
  const STRATEGY_LABELS = new Map([['self_split', 'self-split'], ['split_remaining', 'split remaining'], ['replan', 're-plan'],
    ['design', 'writes AUTOGEN-TESTS.sh'], ['integration', '']]);   // '' = the kind already says it
  const STATUS_LABELS = new Map([['split_done', 'split (history)']]);   // a split superseded when its parent was reopened
  let generation = 0, ui = null, timer = null, ticker = null, reading = false, controllers = new Set();
  let current = null, tasks = {}, selected = '', pending = false, draftId = '';

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function button(text, fn, cls = '') {
    const node = el('button', 'btn ' + cls, text); node.type = 'button'; node.addEventListener('click', fn); return node;
  }
  function section(title, hint) {
    const node = el('section', 'unit'); node.append(el('h2', 'lbl', title));
    if (hint) node.append(el('p', 'ag-note', hint));
    return node;
  }
  function details(title, body, key) {
    const panel = el('details'); if (key) panel.dataset.key = key;
    panel.append(el('summary', '', title), body); return panel;
  }
  function field(label, input, hint) {
    input.setAttribute('aria-label', label);
    const wrap = el('label', 'ag-field'); wrap.append(el('span', 'ag-label', label), input);
    if (hint) wrap.append(el('span', 'ag-hint', hint));
    return wrap;
  }
  function toggle(label, checked) {
    const input = el('input'); input.type = 'checkbox'; input.checked = checked;
    const wrap = el('label', 'ag-check'); wrap.append(input, el('span', '', label)); return {wrap, input};
  }
  function chip(status) {
    const value = String(status || 'unknown');
    return el('span', 'ag-chip ag-s-' + (/^[a-z_]{1,30}$/.test(value) ? value : 'unknown'), STATUS_LABELS.get(value) || value.replaceAll('_', ' '));
  }
  function label(map, value) { return map.has(value) ? map.get(value) : value; }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }
  function agentCap(budget) {
    const max = budget?.agents_max;
    return max === 0 ? 'unlimited' : Number.isInteger(max) && max > 0 ? String(max) : '?';
  }
  function untilDone(run) { return run?.policy?.until_done === true || run?.summary?.until_done === true; }
  function quiet(run) {
    // only an owner action changes these, so they are not polled; a stuck run whose cancel is pending still is
    return TERMINAL.has(run.status) || (run.status === 'stuck' && run.cancel_requested !== true);
  }
  function note(text, bad = false) {
    if (!ui) return;
    ui.message.textContent = text; ui.message.classList.toggle('ag-error', bad);
  }
  function save(id, isPending = false) {
    selected = id; pending = isPending;
    try { if (id) localStorage.setItem(SAVED, JSON.stringify({id, pending: isPending})); else localStorage.removeItem(SAVED); } catch (_) { /* Observation works without storage. */ }
  }
  function restore() {
    try {
      const value = JSON.parse(localStorage.getItem(SAVED) || 'null');
      if (value && RUN_ID.test(value.id)) { selected = value.id; pending = value.pending === true; }
    } catch (_) { /* A corrupt preference is ignored and never acted on. */ }
  }
  function newDraftId() {
    const random = crypto.randomUUID ? crypto.randomUUID() :
      Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
    return 'autogen-ui-' + random;
  }
  async function expectedRunId(requestId) {
    // The coordinator derives the run id from the request id, so a lost response can still be observed.
    try {
      const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(requestId));
      return 'autogen-' + Array.from(new Uint8Array(bytes), n => n.toString(16).padStart(2, '0')).join('').slice(0, 24);
    } catch (_) { return ''; }
  }
  function alive(g) { return ui && g === generation && ui.root.isConnected && location.hash === '#autogen'; }
  async function request(path, body) {
    const read = body === undefined, control = read ? new AbortController() : null;
    if (control) controllers.add(control);
    try {
      const response = await fetch(API + path, {
        method: read ? 'GET' : 'POST', cache: 'no-store', credentials: 'same-origin',
        ...(control ? {signal: control.signal} : {}),
        ...(!read ? {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {}),
      });
      let value = null; try { value = await response.json(); } catch (_) { /* An old server may answer with HTML. */ }
      if (!response.ok || !value || typeof value.error === 'string') {
        const error = new Error(typeof value?.error === 'string' ? value.error : response.status === 403 ? 'Owner access is required.' :
          response.status === 404 || response.status === 503 ? 'The autogen service is not available yet (the host may need its update restarted).' :
            'The autogen service could not complete this request.');
        error.status = response.status; throw error;
      }
      return value;
    } finally { if (control) controllers.delete(control); }
  }
  function list(value) { return Array.isArray(value) ? value : []; }
  function when(seconds) {
    const n = Number(seconds); if (!Number.isFinite(n) || n <= 0) return 'unknown';
    try { return new Date(n * 1000).toLocaleString(); } catch (_) { return String(n); }
  }
  function span(seconds) {
    const s = Math.max(0, Math.floor(seconds)), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
    return (h ? h + ' h ' : '') + (h || m ? m + ' min ' : '') + (s % 60) + ' s';
  }
  function safeAgent(id) { return typeof id === 'string' && /^[A-Za-z0-9_.-]{1,100}$/.test(id) ? id : ''; }
  function terminalUrl(attempt) {
    const step = list(tasks[attempt.task_id]?.steps)[0];
    if (typeof step?.url === 'string' && /^\/terminal\.html\?session=[A-Za-z0-9_.-]+(&node=[A-Za-z0-9_.-]*)?$/.test(step.url)) return step.url;
    const agent = safeAgent(attempt.agent_id || step?.agent_id);
    return agent ? '/terminal.html?session=' + encodeURIComponent(agent) : '';
  }

  // ------------------------------------------------------------------ form
  function setControls() {
    if (!ui) return;
    ui.start.disabled = !ui.ready || ui.starting || ui.creating;
    ui.create.disabled = ui.creating || ui.starting;
    const status = current?.status, stuck = status === 'stuck' && current.cancel_requested !== true;   // a pending cancel ends it instead
    ui.cancel.disabled = !current || ui.controlling || TERMINAL.has(status) || current.cancel_requested === true;
    ui.resume.disabled = !current || ui.controlling || !(status === 'unknown' || stuck || (current.resume_required === true && !TERMINAL.has(status)));
    ui.stuckHint.hidden = !stuck; ui.extendBox.hidden = !stuck;
    if (stuck) paintExtend();
    if (stuck) ui.resume.setAttribute('aria-describedby', ui.stuckHint.id); else ui.resume.removeAttribute('aria-describedby');
    ui.refreshRun.disabled = !selected || ui.controlling;
    ui.draftLine.textContent = 'Request id ' + draftId + ' · kept until a start succeeds, so sending it again never starts a second run.';
  }
  function fill(select, rows, value, empty) {
    select.replaceChildren();
    if (empty !== undefined) { const option = el('option', '', empty); option.value = ''; select.append(option); }
    for (const row of rows) { const option = el('option', '', row.title); option.value = row.id; option.disabled = !!row.disabled; select.append(option); }
    if ([...select.options].some(option => option.value === value && !option.disabled)) select.value = value;
  }
  function paintAgentChoices() {
    const data = ui?.catalog; if (!data) return;
    const specs = data.specs || {};
    const engine = ui.engine.value || (specs.agy ? 'agy' : Object.keys(specs)[0] || '');
    fill(ui.engine, Object.entries(specs).map(([id, spec]) => ({id, title: spec?.title || id})), engine);
    fill(ui.model, list(data.models?.[ui.engine.value]).filter(row => row && typeof row.id === 'string')
      .map(row => ({id: row.id, title: row.title || row.id})), ui.model.value, 'Engine default');
    fill(ui.effort, list(specs[ui.engine.value]?.efforts).filter(id => typeof id === 'string' && id)
      .map(id => ({id, title: data.effortTitles?.[id] || id})), ui.effort.value, 'Engine default');
    fill(ui.node, list(data.nodes).filter(node => node && typeof node.id === 'string').map(node => ({id: node.id,
      title: (node.label || node.name || node.id) + (node.online === false ? ' · offline' : ''), disabled: node.online === false})),
    ui.node.value, 'Choose a machine');
  }
  function paintPolicy(cat) {
    const limits = cat.limits || {}, defaults = cat.defaults || {};
    for (const [key] of INTS) {
      const input = ui.policy[key], bounds = limits[key];
      if (!Array.isArray(bounds) || bounds.length !== 2) throw new Error('The autogen catalogue has no limit for ' + key + '.');
      input.min = bounds[0]; input.max = bounds[1]; input.step = 1;
      if (!ui.initialized) input.value = defaults[key];
    }
    for (const [key, , unit] of TIMES) {
      const input = ui.policy[key], bounds = limits[key];
      if (!Array.isArray(bounds) || bounds.length !== 2) throw new Error('The autogen catalogue has no limit for ' + key + '.');
      input.min = bounds[0] / unit; input.max = bounds[1] / unit; input.step = 'any';
      if (!ui.initialized) input.value = defaults[key] / unit;
    }
    const fb = limits.feedback_chars;
    if (Array.isArray(fb)) { ui.policy.feedback_chars.min = fb[0]; ui.policy.feedback_chars.max = fb[1]; }
    if (!ui.initialized) {
      ui.policy.feedback_chars.value = defaults.feedback_chars;
      ui.perpetual.checked = defaults.perpetual === true;
      ui.syntax.checked = defaults.syntax !== false;
      ui.requireChange.checked = defaults.require_change !== false;
    }
    ui.v2 = V2_INTS.every(([key]) => Array.isArray(limits[key]) && limits[key].length === 2 && Number.isInteger(defaults[key])) &&
      V2_FLAGS.every(([key]) => typeof defaults[key] === 'boolean');
    for (const [key] of V2_INTS) {
      const input = ui.policy[key];
      ui.v2Parts[key].hidden = !ui.v2; input.disabled = !ui.v2;   // disabled: never validated or sent
      if (!ui.v2) continue;
      input.min = limits[key][0]; input.max = limits[key][1]; input.step = 1;
      if (!ui.v2Initialized) input.value = defaults[key];
    }
    for (const [key] of V2_FLAGS) {
      const flag = ui.flags[key];
      flag.wrap.hidden = !ui.v2; flag.input.disabled = !ui.v2;
      if (ui.v2 && !ui.v2Initialized) flag.input.checked = defaults[key] === true;
    }
    if (ui.v2) ui.v2Initialized = true;
    ui.v2Note.hidden = ui.v2;
    ui.limits = limits; ui.defaults = defaults; paintUntil();
    const chosen = new Set(ui.initialized ? ui.strategies.filter(s => s.input.checked).map(s => s.id) : list(defaults.strategies));
    ui.strategyBox.replaceChildren(); ui.strategies = [];
    for (const id of list(cat.strategies)) {
      const box = toggle(STRATEGY_TITLES[id] || id, chosen.has(id)); box.input.value = id;
      ui.strategyBox.append(box.wrap); ui.strategies.push({id, input: box.input});
    }
    ui.limitsNote.textContent = 'Limits from the autogen catalogue (version ' + cat.version + '): ' +
      Object.entries(limits).map(([key, bounds]) => key + ' ' + list(bounds).join('–')).join(', ') + '.' +
      (ui.v2 ? ' With Until done, a blank or 0 agents_max or wall_seconds means unlimited; a value is a safety cap.' : '');
  }
  function paintUntil(changed = false) {
    if (!ui?.limits) return;
    const on = ui.v2 === true && ui.flags.until_done.input.checked;
    for (const key of UNLIMITED) {
      const input = ui.policy[key], unit = unitOf(key), bounds = ui.limits[key];
      if (Array.isArray(bounds)) input.min = on ? 0 : bounds[0] / unit;
      input.required = !on;
      // the toggle promises no count or clock cap, so switching it on blanks both (unlimited); switching it off restores them
      if (changed && on) { ui.capped[key] = input.value; input.value = ''; }
      else if (changed && !(Number(input.value) > 0)) input.value = Number(ui.capped[key]) > 0 ? ui.capped[key] : ui.defaults[key] / unit;
      ui.hints[key].textContent = on ? 'blank or 0 = unlimited' : '';
    }
    for (const key of NOT_CAPS) ui.hints[key].textContent = on ? 'Not a cap until done' : '';
  }
  function unitOf(key) { return TIMES.find(row => row[0] === key)?.[2] || 1; }
  async function loadCatalogs(g = generation) {
    if (!alive(g)) return;
    ui.ready = false; setControls();
    try {
      const [agents, cat] = await Promise.all([request('catalog'), request('autogen/catalog')]);
      if (!alive(g)) return;
      if (!agents.specs || typeof agents.specs !== 'object' || !cat.limits) throw new Error('The catalogue response is incomplete. Refresh after the host update.');
      ui.catalog = agents; paintAgentChoices(); paintPolicy(cat);
      ui.initialized = true; ui.ready = true; setControls();
      if (!selected) note('Ready. Start is the only control that launches agents; reading runs never does.');
    } catch (error) {
      if (!alive(g) || error.name === 'AbortError') return;
      ui.ready = false; setControls(); note(error.message + ' Reload the catalogue to try again; nothing was launched.', true);
    }
  }
  function parseCommands(text) { return text.split('\n').map(line => line.trim()).filter(Boolean); }
  function buildBody() {
    const lines = ui.statements.value.split('\n').map(line => line.trim()).filter(Boolean);
    if (!lines.length) throw new Error('Write at least one statement, one per line.');
    if (lines.length > 64) throw new Error('Use at most 64 statements per run.');
    const short = lines.findIndex(line => line.length < 20);
    if (short >= 0) throw new Error('Statement ' + (short + 1) + ' is shorter than 20 characters; each line is one full, self-contained statement.');
    const cwd = ui.cwd.value.trim();
    if (!cwd.startsWith('/')) throw new Error('Give the workspace as an absolute folder, or create one by name.');
    if (!ui.node.value) throw new Error('Choose the execution machine explicitly.');
    if (!ui.engine.value) throw new Error('Choose an agent type.');
    const policy = {};
    for (const [key] of INTS) policy[key] = Number(ui.policy[key].value);
    for (const [key, , unit] of TIMES) policy[key] = Math.round(Number(ui.policy[key].value) * unit);
    if (ui.v2) for (const [key] of V2_INTS) policy[key] = Number(ui.policy[key].value);
    if (ui.v2 && ui.flags.until_done.input.checked) {
      for (const key of UNLIMITED) {
        // until done: a blank cap is left out (the server reads it as unlimited), 0 is unlimited, a value is a safety cap
        if (!ui.policy[key].value.trim()) { delete policy[key]; continue; }
        const low = ui.limits[key][0], title = [...INTS, ...TIMES].find(row => row[0] === key)[1];
        if (policy[key] !== 0 && policy[key] < low) throw new Error(title + ' must be blank or 0 (unlimited), or a cap of at least ' + low + (unitOf(key) > 1 ? ' seconds.' : '.'));
      }
    }
    policy.feedback_chars = Number(ui.policy.feedback_chars.value);
    for (const [key, value] of Object.entries(policy)) if (!Number.isInteger(value)) throw new Error(key + ' must be a whole number within its limit.');
    policy.strategies = ui.strategies.filter(s => s.input.checked).map(s => s.id);
    if (!policy.strategies.length) throw new Error('Choose at least one regeneration strategy.');
    policy.perpetual = ui.perpetual.checked; policy.syntax = ui.syntax.checked; policy.require_change = ui.requireChange.checked;
    if (ui.v2) for (const [key] of V2_FLAGS) policy[key] = ui.flags[key].input.checked;
    policy.checks = {};
    for (const [n, raw] of ui.checks.value.split('\n').entries()) {
      const line = raw.trim(); if (!line) continue;
      const match = /^(\d{1,2})\s*:\s*(.+)$/.exec(line);
      if (!match || Number(match[1]) < 1 || Number(match[1]) > lines.length) throw new Error('Public checks line ' + (n + 1) + ' must read "STATEMENT_NUMBER: command", numbered 1 to ' + lines.length + '.');
      const key = String(Number(match[1]) - 1);
      (policy.checks[key] = policy.checks[key] || []).push(match[2].trim());
    }
    policy.final = parseCommands(ui.final.value);
    policy.hidden = parseCommands(ui.hidden.value);
    const body = {client_request_id: draftId, instruction: lines.join('\n'), engine: ui.engine.value, node: ui.node.value, cwd,
      headless: ui.headless.checked, autogen: policy};
    if (ui.model.value) body.model = ui.model.value;
    if (ui.effort.value) body.effort = ui.effort.value;
    if (ui.context.value.trim()) body.context_note = ui.context.value;
    return body;
  }
  async function start() {
    if (!ui || ui.starting || !ui.ready || !ui.form.reportValidity()) return;
    let body;
    try { body = buildBody(); } catch (error) { note(error.message, true); return; }
    const g = generation, sentId = body.client_request_id;
    ui.starting = true; setControls(); note('Sending the start request once…');
    const expected = await expectedRunId(sentId);
    try {
      const value = await request('autogen/start', body);
      if (!value.run || !RUN_ID.test(value.run.id)) throw Object.assign(new Error('The start response has no run identity.'), {status: 0});
      if (draftId === sentId) draftId = newDraftId();  // only a recorded start retires the draft id
      save(value.run.id, false);
      if (!alive(g)) return;
      current = null; tasks = {};
      note(value.duplicate ? 'This request was already recorded; showing the existing run. Nothing new was launched.' :
        'Run recorded. The coordinator launches its first candidates; this page only observes from here.');
      show(value.run); history(g); refresh(g);
    } catch (error) {
      if (!alive(g)) return;
      if (error.status === 409) {
        // A digest conflict proves the earlier request with this id is recorded.
        if (draftId === sentId) draftId = newDraftId();
        note(error.message + ' The earlier request with that id is listed under Runs. A new request id is ready for this edited draft.', true);
        history(g);
      } else if ([400, 403, 404].includes(error.status)) {
        note('Start refused; no run was recorded. ' + error.message, true);
      } else {
        if (expected) { save(expected, true); current = null; paintRun(); refresh(g); }
        note('Start outcome is unknown. ' + error.message + ' The request id is kept: pressing Start again with the same draft is duplicate-safe' +
          (expected ? ', and run ' + expected + ' is being observed.' : '.'), true);
      }
    } finally { if (ui && g === generation) { ui.starting = false; setControls(); } }
  }
  async function createWorkspace() {
    if (!ui || ui.creating) return;
    const name = ui.project.value.trim(), g = generation;
    if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name)) { note('Use a project name of 1–64 lowercase letters, digits, hyphens or underscores, starting with a letter or digit.', true); return; }
    ui.creating = true; setControls();
    try {
      const result = await request('workspace/create', {name});
      if (typeof result.cwd !== 'string' || !result.cwd.startsWith('/')) throw new Error('No workspace folder was returned; creating the same name again reconnects to it.');
      if (!alive(g)) return;
      ui.cwd.value = result.cwd;
      note((result.created ? 'Workspace created: ' : 'Existing managed workspace: ') + result.cwd);
    } catch (error) { if (alive(g)) note('Workspace not created. ' + error.message, true); }
    finally { if (ui && g === generation) { ui.creating = false; setControls(); } }
  }

  // ------------------------------------------------------------------ runs
  async function history(g = generation) {
    if (!alive(g)) return;
    try {
      const value = await request('autogen'); if (!alive(g)) return;
      ui.runs.replaceChildren();
      for (const row of list(value.runs)) {
        if (!row || !RUN_ID.test(row.id)) continue;
        const line = el('div', 'ag-run-row' + (row.id === selected ? ' ag-selected' : ''));
        const text = el('div', 'ag-grow');
        const head = el('div', 'ag-row-head'); head.append(chip(row.status), el('span', 'ag-mono', row.id));
        text.append(head, el('p', 'ag-note ag-clip', list(row.lines)[0] || ''),
          el('p', 'ag-meta', list(row.lines).length + ' statements · agents ' + (row.budget?.agents_started ?? 0) + '/' + agentCap(row.budget) +
            (untilDone(row) ? ' · until done' : '') + ' · ' + when(row.created)));
        const open = button('Open', () => select(row.id), 'ghost'); open.setAttribute('aria-label', 'Open run ' + row.id);
        line.append(text, open); ui.runs.append(line);
      }
      if (!ui.runs.childElementCount) ui.runs.append(el('p', 'ag-note', 'No autogen runs yet.'));
    } catch (error) { if (alive(g) && error.name !== 'AbortError') { ui.runs.replaceChildren(el('p', 'ag-note ag-error', error.message)); } }
  }
  function select(id) {
    if (!ui || !RUN_ID.test(id)) return;
    save(id, false); current = null; tasks = {}; ui.extendAgents.value = ''; ui.extendHours.value = ''; paintRun();
    for (const row of ui.runs.querySelectorAll('.ag-run-row')) row.classList.toggle('ag-selected', row.querySelector('.ag-mono')?.textContent === id);
    refresh();
  }
  function schedule(g) {
    clearTimeout(timer); timer = null;
    if (alive(g) && selected && (pending || !current || !quiet(current))) timer = setTimeout(() => refresh(g), POLL_MS);
  }
  async function refresh(g = generation) {
    if (!alive(g) || !selected) return;
    if (reading || document.hidden) { schedule(g); return; }
    reading = true; const id = selected;
    try {
      const value = await request('autogen/get?id=' + encodeURIComponent(id) + '&tasks=1');
      if (!alive(g) || id !== selected) return;
      if (!value.run || value.run.id !== id) throw new Error('The run response does not match the selected run.');
      tasks = value.run.tasks && typeof value.run.tasks === 'object' ? value.run.tasks : {};
      if (pending) save(id, false);
      show(value.run);
    } catch (error) {
      if (!alive(g) || error.name === 'AbortError' || id !== selected) return;
      if (error.status === 404 && pending) note('No record yet for ' + id + ' from the unconfirmed start. Observing only; nothing is resent.', true);
      else if (error.status === 404) { save('', false); current = null; paintRun(); note('That run is not recorded here. ' + error.message, true); }
      else note('Run status could not be read. ' + error.message, true);
    } finally {
      reading = false;
      if (alive(g) && selected && id !== selected) refresh(g);  // a run chosen during this read is read now
      else schedule(g);
    }
  }
  function paintExtend() {
    // 0 (unlimited) is offered only for an until-done run; the bounds are the catalogue's (the server checks them again)
    const until = untilDone(current), agents = ui.limits?.agents_max, wall = ui.limits?.wall_seconds;
    ui.extendAgents.min = until ? 0 : Array.isArray(agents) ? agents[0] : 1;
    if (Array.isArray(agents)) ui.extendAgents.max = agents[1];
    ui.extendHours.min = until ? 0 : Array.isArray(wall) ? wall[0] / 3600 : 0;
    if (Array.isArray(wall)) ui.extendHours.max = wall[1] / 3600;
    ui.extendHint.textContent = (until ? 'Blank leaves a cap as it is; 0 lifts it (unlimited). ' : 'Blank leaves a cap as it is. ') +
      'Hours count from the resume.';
  }
  function readExtend() {
    // Returns the extend object for a stuck run's resume, null for none; throws when a typed cap is not acceptable.
    const until = untilDone(current), extend = {};
    for (const [key, input, unit, title] of [['agents_max', ui.extendAgents, 1, 'agents'], ['wall_seconds', ui.extendHours, 3600, 'hours']]) {
      if (!input.reportValidity()) throw new Error('Fix ' + title + ' before resuming: ' + (input.validationMessage || 'the value is outside its limit').replace(/\.$/, '') + '.');
      if (!input.value.trim()) continue;                                 // blank: not sent
      const value = Math.round(Number(input.value) * unit), low = ui.limits?.[key]?.[0] || 0;
      if ((value === 0 && !until) || (value !== 0 && value < low)) {
        throw new Error(title + ' must be blank' + (until ? ', 0 (unlimited)' : '') + ' or a cap of at least ' + low + (unit > 1 ? ' seconds.' : '.'));
      }
      extend[key] = value;
    }
    return Object.keys(extend).length ? extend : null;
  }
  async function control(action) {
    if (!ui || ui.controlling || !current || !selected) return;
    if (action === 'cancel' && (TERMINAL.has(current.status) || current.cancel_requested)) return;
    if (action === 'resume' && ui.resume.disabled) return;
    const wasStuck = current.status === 'stuck', body = {id: selected, action};
    if (action === 'resume' && wasStuck && !ui.extendBox.hidden) {
      try { const extend = readExtend(); if (extend) body.extend = extend; } catch (error) { note(error.message, true); return; }
    }
    const g = generation, id = selected; ui.controlling = true; setControls();
    try {
      const value = await request('autogen/control', body);
      if (body.extend && ui && g === generation) { ui.extendAgents.value = ''; ui.extendHours.value = ''; }
      if (alive(g) && value.run?.id === id && id === selected) show(value.run);
      if (alive(g)) note(action === 'cancel' ? 'Cancel recorded. The coordinator cancels running attempts on its next pass.' :
        wasStuck ? 'Resume recorded. Stuck statements reopen with their stall count cleared; everything they tried stays recorded.' :
          'Resume recorded. The coordinator re-attaches; recorded attempts are observed, never launched twice.');
    } catch (error) {
      // a refusal changed nothing: a 409 carries the server's own instructions (a spent cap), shown verbatim
      if (alive(g)) note(error.status === 409 ? error.message : [400, 403, 404].includes(error.status) ?
        'The ' + action + ' request was refused; nothing changed. ' + error.message :
        'The ' + action + ' request has an uncertain outcome. Refresh before another action. ' + error.message, true);
    } finally { if (ui && g === generation) { ui.controlling = false; setControls(); history(g); refresh(g); } }
  }

  // ------------------------------------------------------------------ run view
  function paintRun() {
    if (!ui) return;
    ui.run.hidden = !selected;
    if (!current) {
      ui.runTitle.textContent = selected ? 'Reading run ' + selected + '…' : '';
      for (const part of [ui.runHead, ui.budget, ui.tree, ui.finalBox]) part.replaceChildren();
    }
    setControls();
  }
  function tick() {
    if (!ui || !current) return;
    const raw = current.budget?.deadline, deadline = Number(raw), ended = TERMINAL.has(current.status);
    ui.countdown.textContent = raw === null ? (ended ? 'Run ended · it had no deadline' : 'No deadline: no clock ends this run') :
      !Number.isFinite(deadline) || deadline <= 0 ? 'Deadline unknown' : ended ? 'Run ended · deadline was ' + when(deadline) :
        deadline * 1000 <= Date.now() ? 'Deadline passed ' + when(deadline) : 'Deadline in ' + span(deadline - Date.now() / 1000) + ' (' + when(deadline) + ')';
  }
  function checkList(verdict) {
    const box = el('div', 'ag-checks');
    for (const check of list(verdict?.checks)) {
      const row = el('div', 'ag-check-row ' + (check.passed ? 'ag-pass' : 'ag-fail'));
      const head = el('p', 'ag-meta');
      head.append(el('b', '', check.passed ? 'PASS ' : 'FAIL '), document.createTextNode(String(check.kind || 'check') +
        (check.file ? ' · ' + check.file : '') + (check.command ? ' · ' + check.command : '')));
      if (typeof check.sandbox === 'string' && /^[A-Za-z0-9_.-]{1,32}$/.test(check.sandbox)) {
        // a model-written (designed) test runs inside this sandbox, e.g. the repository's Landlock launcher
        const tag = el('span', 'ag-tag', check.sandbox); tag.title = 'Ran inside the ' + check.sandbox + ' sandbox'; head.append(' ', tag);
      }
      row.append(head);
      if (check.public === false) row.append(el('p', 'ag-note', 'Hidden or private check: its output is never shown to agents and is withheld here.'));
      else if (check.output) row.append(el('pre', 'ag-code', check.output));
      box.append(row);
    }
    if (!box.childElementCount) box.append(el('p', 'ag-note', 'No code checks were recorded.'));
    if (verdict && verdict.files_changed !== undefined && verdict.files_changed !== null) box.append(el('p', 'ag-meta', 'Files changed: ' + verdict.files_changed));
    return box;
  }
  function attemptRow(node, attempt) {
    const row = el('li', 'ag-attempt');
    const head = el('div', 'ag-row-head');
    head.append(el('span', 'ag-mono', attempt.id || ''), chip(attempt.status));
    if (attempt.failure) head.append(el('span', 'ag-failure', attempt.failure));
    if (node.winner && node.winner === attempt.id) head.append(el('span', 'ag-winner', 'winner'));
    row.append(head);
    row.append(el('p', 'ag-meta', [label(KIND_LABELS, attempt.kind), label(STRATEGY_LABELS, attempt.strategy),
      attempt.engine || attempt.node ? (attempt.engine || '?') + '@' + (attempt.node || '?') : '',   // an integration check runs in code
      attempt.model ? 'model ' + attempt.model : '', attempt.generation ? 'generation ' + attempt.generation : '',
      attempt.from ? 'continues ' + attempt.from : '', attempt.started ? 'started ' + when(attempt.started) : ''].filter(Boolean).join(' · ')));
    if (attempt.error) row.append(el('p', 'ag-note', attempt.error));
    const links = el('div', 'ag-links'), url = terminalUrl(attempt);
    if (url) { const a = el('a', 'btn sm ghost', 'Agent terminal'); a.href = url; a.setAttribute('aria-label', 'Agent terminal for ' + attempt.id); links.append(a); }
    if (attempt.task_id && /^task-[a-f0-9]{32}$/.test(attempt.task_id)) {
      const a = el('a', 'btn sm ghost', 'Task record'); a.href = API + 'tasks/get?id=' + encodeURIComponent(attempt.task_id);
      a.setAttribute('aria-label', 'Task record for ' + attempt.id); links.append(a);
    }
    if (links.childElementCount) row.append(links);
    const key = (node.id || '') + '/' + (attempt.id || '');
    if (attempt.verdict) {
      const checks = list(attempt.verdict.checks);
      row.append(details('Verdict · ' + (attempt.verdict.passed ? 'passed' : 'failed') + ' · ' + checks.length + ' checks', checkList(attempt.verdict), key + '/verdict'));
    }
    if (list(attempt.split).length) {
      const lines = el('ol', 'ag-list'); for (const line of attempt.split) lines.append(el('li', '', line));
      row.append(details('Validated split · ' + attempt.split.length + ' statements', lines, key + '/split'));
    }
    if (attempt.checkpoint) {
      const box = el('div');
      for (const part of ['done', 'left', 'files']) box.append(el('p', 'ag-meta', part + ': ' + (list(attempt.checkpoint[part]).join('; ') || 'none')));
      row.append(details('Checkpoint', box, key + '/checkpoint'));
    }
    return row;
  }
  function nodeFacts(node, until, limit) {
    const parts = [], count = plural;
    const progress = node.progress && typeof node.progress === 'object' ? node.progress : {};
    const names = list(progress.files).filter(name => typeof name === 'string');
    const files = Array.isArray(progress.files) ? names.length : Number(progress.files) || 0;
    const checks = Number(progress.checks) || 0, done = Number(progress.done) || 0, got = [];
    if (files > 0) got.push(count(files, 'file', 'files') + (names.length ? ' (' + names.slice(0, 4).join(', ') + (names.length > 4 ? ', +' + (names.length - 4) + ' more' : '') + ')' : ''));
    if (checks > 0) got.push(count(checks, 'check', 'checks') + ' passed');
    if (done > 0) got.push(count(done, 'checkpoint item', 'checkpoint items') + ' done');
    if (got.length) parts.push('Progress: ' + got.join(', '));
    const stale = Number(node.stale) || 0;
    if (stale > 0) parts.push(until && limit ? stale + ' of ' + limit + ' attempts without progress' : count(stale, 'attempt', 'attempts') + ' without progress');
    if (node.perpetual) parts.push(count(Number(node.items_total) || 0, 'item', 'items') + ' indexed');
    return parts.join(' · ');
  }
  function nodeView(node, context) {
    const depth = Math.max(0, Math.min(3, Number(node.depth) || 0));
    const box = el('div', 'ag-node' + (depth ? ' ag-child' : '')); box.style.setProperty('--depth', String(depth)); box.dataset.depth = String(depth);
    const head = el('div', 'ag-row-head');
    const label = node.parent ? node.id : 'Statement ' + ((Number(node.index) || 0) + 1);
    head.append(el('strong', '', label), el('span', 'ag-mono', node.parent ? 'depth ' + node.depth : node.id), chip(node.status));
    if (node.generation) head.append(el('span', 'ag-meta', 'generation ' + node.generation));
    if (node.perpetual) head.append(el('span', 'ag-meta', 'perpetual'));
    const handoffStale = Number(node.handoff_stale) || 0, integrations = Number(node.integrations) || 0;
    if (handoffStale > 0) head.append(el('span', 'ag-tag', plural(handoffStale, 'handoff', 'handoffs') + ' without progress'));
    if (integrations > 0) head.append(el('span', 'ag-tag', 'reopened ' + integrations + '× after integration'));
    box.append(head, el('p', 'ag-statement', node.statement || ''));
    if (node.error) box.append(el('p', 'ag-note ag-error', node.error));
    const facts = nodeFacts(node, context.until, context.limit);
    if (facts) box.append(el('p', 'ag-meta', facts));
    const attempts = el('ol', 'ag-attempts');
    for (const attempt of list(node.attempts)) attempts.append(attemptRow(node, attempt));
    if (attempts.childElementCount) box.append(attempts); else box.append(el('p', 'ag-meta', 'No attempts yet.'));
    const decisions = list(node.decisions);
    if (decisions.length) {
      const log = el('ol', 'ag-list ag-log');
      for (const d of decisions.slice().reverse()) log.append(el('li', '', when(d.at) + ' · ' + (d.action || '?') + ' · ' + (d.reason || '')));
      box.append(details('Decisions · ' + decisions.length, log, node.id + '/decisions'));
    }
    return box;
  }
  function show(run) {
    if (!ui || run.id !== selected) return;
    current = run; ui.run.hidden = false;
    const open = new Set(Array.from(ui.root.querySelectorAll('details[open][data-key]'), d => d.dataset.key));
    ui.runTitle.textContent = 'Run ' + run.id;
    const head = el('div', 'ag-row-head'); head.append(chip(run.status));
    if (untilDone(run)) head.append(el('span', 'ag-meta', 'until done'));
    if (run.cancel_requested) head.append(el('span', 'ag-meta', 'cancel requested'));
    head.append(el('span', 'ag-meta', (run.base?.engine || '?') + '@' + (run.base?.node || '?') + ' · ' + (run.base?.cwd || '')));
    ui.runHead.replaceChildren(head);
    if (run.error) ui.runHead.append(el('p', 'ag-note ag-error', run.error));
    if (run.resume_required) ui.runHead.append(el('p', 'ag-note ag-warn', 'No coordinator is driving this run (for example after a host restart). Resume re-attaches it; recorded attempts are observed, never launched twice.'));
    const budget = run.budget || {}, started = Number(budget.agents_started) || 0, cap = agentCap(budget);
    const parts = [el('p', 'ag-meta', 'Agents started ' + started + ' of ' + cap)];
    if (/^\d+$/.test(cap)) {   // an unlimited (or unknown) cap has no fraction to draw
      const max = Number(cap), bar = el('div', 'ag-bar'), fillBar = el('span');
      fillBar.style.width = Math.min(100, started / max * 100) + '%'; bar.append(fillBar);
      bar.setAttribute('role', 'progressbar'); bar.setAttribute('aria-label', 'Agents started');
      bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', String(max)); bar.setAttribute('aria-valuenow', String(started));
      parts.push(bar);
    }
    ui.budget.replaceChildren(...parts, ui.countdown); tick();
    const byId = new Map(list(run.nodes).map(node => [node.id, node])), seen = new Set(), views = [];
    const context = {until: untilDone(run), limit: Number(run.policy?.novelty_limit) || 0};
    const walk = id => {
      const node = byId.get(id); if (!node || seen.has(id)) return;
      seen.add(id); views.push(nodeView(node, context)); for (const child of list(node.children)) walk(child);
    };
    for (const id of list(run.order)) walk(id);
    for (const node of list(run.nodes)) walk(node.id);
    ui.tree.replaceChildren(...views);
    if (!views.length) ui.tree.append(el('p', 'ag-note', 'No statements are recorded.'));
    ui.finalBox.replaceChildren();
    if (run.final) {
      ui.finalBox.append(el('p', 'ag-meta', 'Final checks ' + (run.final.passed ? 'passed' : 'failed')), checkList(run.final));
    } else ui.finalBox.append(el('p', 'ag-note', list(run.policy?.final).length ? 'Final checks run after every statement is accepted: ' + run.policy.final.join(' ; ') : 'No final checks were set.'));
    for (const d of ui.root.querySelectorAll('details[data-key]')) if (open.has(d.dataset.key)) d.open = true;
    setControls();
  }

  // ------------------------------------------------------------------ lifecycle
  function stop() {
    generation++; clearTimeout(timer); timer = null; clearInterval(ticker); ticker = null;
    for (const controller of controllers) controller.abort(); controllers.clear();
    reading = false; ui = null;
  }
  function render(mount) {
    stop(); const g = generation; restore(); current = null; tasks = {};
    if (!draftId) draftId = newDraftId();
    const root = el('div', 'autogen'); mount.replaceChildren(root);
    const intro = section('Autogen', 'Self-replicating agents above Symblic tasks: one agent per statement by default (more candidates when asked), regeneration with another strategy, splits into smaller statements, checkpointed handoffs, and until-done mode with no clock or count caps. Code decides every verdict.');
    root.append(intro);
    const message = el('p', 'ag-note ag-message', 'Reading the agent and autogen catalogues…');
    message.setAttribute('role', 'status'); message.setAttribute('aria-live', 'polite'); root.append(message);

    const draft = section('New run'); const form = el('form', 'ag-form'); form.addEventListener('submit', event => event.preventDefault());
    const statements = el('textarea', 'field'); statements.rows = 7; statements.maxLength = 60000; statements.required = true;
    statements.placeholder = 'Create the file app.js in the folder /srv/symblic/projects/NAME exporting add(a, b) that returns a + b.';
    form.append(field('Statements', statements, 'One statement per line; each line runs in a fresh agent context.'));
    const rules = el('ul', 'ag-list ag-rules');
    for (const text of ['Start each line with an action verb: Create, Extend, Write, Verify…', 'At least 20 characters: one full, self-contained statement per line.',
      'Name the absolute folder (in the folder /home/…) and the exact file in every line.', 'Edits say "keeping every existing part".',
      'Never refer to another line ("the previous file"); fresh agents see only their own line and the context note.',
      'End with a verify statement that runs a concrete check and writes verify.txt in an exact format.']) rules.append(el('li', '', text));
    form.append(details('Statement rules the linter enforces', rules));
    const agentGrid = el('div', 'ag-grid');
    const engine = el('select', 'field'), model = el('select', 'field'), effort = el('select', 'field'), node = el('select', 'field');
    node.required = true;
    engine.addEventListener('change', () => { model.value = ''; effort.value = ''; paintAgentChoices(); });
    agentGrid.append(field('Agent type', engine), field('Machine', node), field('Model', model), field('Effort', effort));
    form.append(agentGrid);
    const cwd = el('input', 'field'); cwd.type = 'text'; cwd.required = true; cwd.maxLength = 1000; cwd.placeholder = '/srv/symblic/projects/NAME';
    form.append(field('Workspace folder', cwd, 'An existing git workspace; candidates work in their own checkouts and the winner is applied here.'));
    const projectRow = el('div', 'ag-inline');
    const project = el('input', 'field'); project.type = 'text'; project.maxLength = 64; project.placeholder = 'project-name';
    const create = button('Create workspace', createWorkspace, 'ghost');
    projectRow.append(field('New workspace name', project), create);
    form.append(projectRow);
    const context = el('textarea', 'field'); context.rows = 3; context.maxLength = 12000;
    form.append(field('Context note', context, 'Shared facts every worker receives with its one statement.'));

    const policyGrid = el('div', 'ag-grid'), policy = {}, hints = {}, v2Parts = {};
    const numberField = (key, title, text = '') => {
      // the hint sits between the label and the input, so the inputs of one grid row stay aligned
      const input = el('input', 'field'); input.type = 'number'; input.required = true; policy[key] = input;
      const wrap = field(title, input), hint = el('span', 'ag-hint', text);
      hint.id = 'ag-hint-' + key; input.setAttribute('aria-describedby', hint.id); wrap.insertBefore(hint, input); hints[key] = hint;
      return wrap;
    };
    for (const [key, title] of [...INTS, ...TIMES]) policyGrid.append(numberField(key, title));
    for (const [key, title, text] of V2_INTS) {
      const wrap = numberField(key, title, text); wrap.hidden = true; policy[key].disabled = true; v2Parts[key] = wrap; policyGrid.append(wrap);
    }
    const flags = {};
    for (const [key, title] of V2_FLAGS) {
      const box = toggle(title, false); box.wrap.hidden = true; box.input.disabled = true; flags[key] = box;
    }
    flags.until_done.input.addEventListener('change', () => paintUntil(true));
    const policyBox = el('div', 'ag-form');
    const limitsNote = el('p', 'ag-meta');
    const v2Note = el('p', 'ag-note', 'This server\'s autogen catalogue has no Until done, test designer or self-split fields yet (the host update needs a restart); runs use the bounded policy.');
    v2Note.hidden = true;
    const strategyBox = el('div', 'ag-checks-grid');
    const perpetual = toggle('Perpetual lane (one generation at a time, re-spawned on the interval)', false);
    const syntax = toggle('Syntax check every named file by extension', true);
    const requireChange = toggle('Refuse "done" when no workspace file changed', true);
    const headless = toggle('Run workers headless', true);
    policyBox.append(flags.until_done.wrap, policyGrid, limitsNote, v2Note, el('span', 'ag-label', 'Regeneration strategies'), strategyBox,
      flags.designer.wrap, flags.self_split.wrap, perpetual.wrap, syntax.wrap, requireChange.wrap, headless.wrap);
    form.append(details('Policy: candidates, regeneration, splits and budget', policyBox, 'form/policy'));

    const checksBox = el('div', 'ag-form');
    const checks = el('textarea', 'field'); checks.rows = 3; checks.placeholder = '1: node --test tests/app.test.js';
    const finalCmds = el('textarea', 'field'); finalCmds.rows = 2; finalCmds.placeholder = 'node --test';
    const hidden = el('textarea', 'field'); hidden.rows = 2; hidden.placeholder = 'node hidden-check.js';
    const feedback = el('input', 'field'); feedback.type = 'number'; feedback.required = true; policy.feedback_chars = feedback;
    checksBox.append(field('Public checks per statement', checks, 'One per line as NUMBER: command (1 is the first statement). Their output is shown to regenerations.'),
      field('Final commands', finalCmds, 'One per line; run in the workspace after every statement is accepted.'),
      field('Hidden commands', hidden, 'One per line; run on the last statement only. Their output never reaches an agent.'),
      field('Feedback characters', feedback));
    form.append(details('Checks', checksBox, 'form/checks'));

    const startButton = button('Start autogen run', start, 'acc'); startButton.disabled = true;
    const reload = button('Reload catalogue', () => loadCatalogs(g), 'ghost');
    const actions = el('div', 'ag-actions'); actions.append(startButton, reload);
    const draftLine = el('p', 'ag-meta ag-mono');
    form.append(actions, draftLine); draft.append(form); root.append(draft);

    const runsSection = section('Runs', 'Opening a run only reads it.');
    const runs = el('div', 'ag-runs');
    runsSection.append(button('Refresh runs', () => history(g), 'ghost'), runs); root.append(runsSection);

    const run = section('Selected run'); run.hidden = true;
    const runTitle = el('h3', 'ag-title'), runHead = el('div'), budget = el('div', 'ag-budget'), countdown = el('p', 'ag-meta');
    const runActions = el('div', 'ag-actions');
    const cancel = button('Cancel run', () => control('cancel'), 'danger'), resume = button('Resume run', () => control('resume'));
    const refreshRun = button('Refresh run', () => refresh(g), 'ghost');
    const forget = button('Close run', () => { save('', false); current = null; tasks = {}; paintRun(); history(g); }, 'ghost');
    runActions.append(cancel, resume, refreshRun, forget);
    const tree = el('div', 'ag-tree'), finalBox = el('div');
    const finalSection = el('div'); finalSection.append(el('h3', 'ag-title', 'Final checks'), finalBox);
    const stuckHint = el('p', 'ag-note ag-warn', STUCK_HINT + '.'); stuckHint.id = 'ag-stuck-hint'; stuckHint.hidden = true;
    const extendBox = el('fieldset', 'ag-extend'); extendBox.hidden = true;
    const extendAgents = el('input', 'field'), extendHours = el('input', 'field'), extendHint = el('p', 'ag-hint');
    extendAgents.type = 'number'; extendAgents.step = 1; extendHours.type = 'number'; extendHours.step = 'any';
    const extendRow = el('div', 'ag-inline'); extendRow.append(field('agents', extendAgents), field('hours', extendHours));
    extendBox.append(el('legend', 'ag-label', 'Raise a spent cap with Resume (optional)'), extendRow, extendHint);
    run.append(runTitle, runHead, budget, runActions, stuckHint, extendBox, el('h3', 'ag-title', 'Statement tree'), tree, finalSection);
    root.append(run);

    ui = {root, message, form, statements, engine, model, effort, node, cwd, project, create, context, policy, limitsNote,
      strategyBox, strategies: [], perpetual: perpetual.input, syntax: syntax.input, requireChange: requireChange.input,
      headless: headless.input, checks, final: finalCmds, hidden, start: startButton, draftLine, runs, run, runTitle, runHead,
      budget, countdown, cancel, resume, refreshRun, tree, finalBox, ready: false, initialized: false, starting: false,
      creating: false, controlling: false, catalog: null, hints, v2Parts, v2Note, flags, stuckHint, extendBox, extendAgents,
      extendHours, extendHint, capped: {}, v2: false,
      v2Initialized: false, limits: null, defaults: null};
    paintRun(); setControls();
    ticker = setInterval(() => { if (alive(g)) tick(); }, 1000);
    loadCatalogs(g); history(g); if (selected) refresh(g);
  }
  window.addEventListener('online', () => { if (ui && selected) refresh(); });
  window.SymblicAutogen = {render, stop};
})();
