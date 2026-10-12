/* Construct: explicit dispatch; observation and reconnect never launch work. */
(() => {
  'use strict';
  const API = '/api/automation/symblic/mica/';
  const SAVED = 'symblic.construct.selection.v1';
  const ID = /^[a-f0-9]{12}$/;
  let generation = 0, statusEpoch = 0, ui = null, timer = null, reading = false, controllers = new Set();
  let current = null, selected = '', pendingLaunch = false;

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function button(text, fn, cls = '') {
    const node = el('button', 'btn ' + cls, text); node.type = 'button'; node.addEventListener('click', fn); return node;
  }
  function section(title, hint) {
    const node = el('section', 'unit'); node.append(el('h2', 'lbl', title));
    if (hint) node.append(el('p', 'mica-note', hint));
    return node;
  }
  function details(title, node) {
    const panel = el('details'); panel.append(el('summary', '', title), node); return panel;
  }
  function field(label, input) {
    input.setAttribute('aria-label', label);
    const wrap = el('label', 'mica-field'); wrap.append(el('span', 'mica-label', label), input); return wrap;
  }
  function note(text, bad = false) {
    if (!ui) return;
    ui.message.textContent = text; ui.message.classList.toggle('mica-error', bad);
  }
  function save(id, pending = false) {
    selected = id; pendingLaunch = pending;
    try { if (id) localStorage.setItem(SAVED, JSON.stringify({id, pending})); else localStorage.removeItem(SAVED); } catch (_) { /* Observation still works without storage. */ }
  }
  function restore() {
    try {
      const value = JSON.parse(localStorage.getItem(SAVED) || 'null');
      if (value && ID.test(value.id)) { selected = value.id; pendingLaunch = value.pending === true; }
    } catch (_) { /* Ignore corrupt local preferences, never execute them. */ }
  }
  function alive(g) { return ui && g === generation && ui.root.isConnected && location.hash === '#construct'; }
  function api(route, body) { return request(API + route, body); }
  async function request(url, body, observation = false) {
    const read = body === undefined, control = read || observation ? new AbortController() : null;
    if (control) controllers.add(control);
    try {
      const response = await fetch(url, {
        method: read ? 'GET' : 'POST', cache: 'no-store', credentials: 'same-origin',
        ...(control ? {signal: control.signal} : {}),
        ...(!read ? {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {}),
      });
      let value = null; try { value = await response.json(); } catch (_) { /* An old server may return HTML. */ }
      if (!response.ok || !value || value.ok === false || typeof value.error === 'string' && !read) {
        const error = new Error(value?.error || (response.status === 403 ? 'Owner access is required.' :
          response.status === 404 || response.status === 503 ? 'The construction service is not available yet.' : 'The construction service could not complete this request.'));
        error.status = response.status; throw error;
      }
      return value;
    } finally { if (control) controllers.delete(control); }
  }
  function number(value) { return Number.isFinite(value) ? String(value) : 'unknown'; }
  function stat(label, value, hint) {
    const node = el('div', 'mica-stat'); node.append(el('span', '', label), el('strong', '', value), el('span', '', hint)); return node;
  }
  function setControls() {
    if (!ui) return;
    ui.plan.disabled = ui.busy || ui.refreshing || !ui.ready || pendingLaunch;
    ui.refreshWorkers.disabled = ui.busy || ui.refreshing || pendingLaunch;
    ui.source.disabled = ui.busy || ui.refreshing || pendingLaunch;
    ui.execute.disabled = ui.busy || current?.can_execute !== true || current?.status !== 'planned';
    ui.resume.disabled = ui.busy || current?.can_resume !== true || current?.status === 'unknown';
    ui.stop.disabled = ui.busy || current?.active !== true;
  }
  function showCurrent(value) {
    if (!ui || value.id !== selected) return;
    current = value; save(value.id, false);
    ui.run.hidden = false;
    const result = value.result || {}, task = value.spec?.task || {};
    const budget = task.budget || task.request?.budget || {};
    const req = result.request || result.proposed_request || task.request;
    ui.runTitle.textContent = value.meta?.title || task.objective || task.request?.objective || 'Construction';
    ui.runId.textContent = 'Run ' + value.id;
    ui.stats.replaceChildren(
      stat('State', value.status || 'unknown', value.active ? 'Worker active' : 'No active worker reported'),
      stat('Reported provider calls', number(result.calls), 'Original limit: ' + number(budget.max_calls)),
      stat('Original time limit', number(budget.wall_seconds) + ' s', 'Planning and execution share this deadline'),
      stat('Reserved or spent calls', number(result.calls_reserved_or_spent), 'A reservation is not an observed provider call'),
    );
    ui.runMessage.textContent = result.error || value.error || (value.status === 'unknown' ?
      'Delivery is unresolved. This run cannot be resumed automatically or sent again.' : value.status === 'planned' ?
      'The proposal is ready. Execute plan continues this run with its remaining original budget.' : value.status === 'done' ?
      'An artifact passed the recorded checks. Review its source and evidence below.' :
      'Status reads do not launch or resume work. Unknown measurements remain unknown.');
    ui.runMessage.classList.toggle('mica-error', ['unknown', 'failed', 'blocked', 'lost'].includes(value.status));
    ui.proposal.replaceChildren();
    if (req) {
      const requirements = section(task.kind === 'forge' ? 'Accepted Forge requirements' : task.kind === 'request' ? 'Requirements' : 'Proposed requirements', task.kind === 'forge' ?
        'These are the accepted requirements in the frozen handoff. The supplied examples express a finite interpretation; completeness remains unassessed.' : task.kind === 'request' ?
        'These requirements and tests were supplied by the caller. The recorded assurance covers the encoded checks.' :
        'Generated requirements and tests are model proposals. Your original objective remains the source of intent.');
      const list = el('ol', 'mica-list');
      for (const row of req.requirements || []) { const item = el('li'); item.append(el('b', '', row.id + ': '), document.createTextNode(row.text || '')); list.append(item); }
      requirements.append(list); ui.proposal.append(requirements);
      const assumptions = section('Assumptions'); const values = el('ul', 'mica-list');
      for (const text of req.assumptions || []) values.append(el('li', '', text));
      assumptions.append(values.childElementCount ? values : el('p', 'mica-note', 'No assumptions were recorded.'));
      ui.proposal.append(assumptions);
      const checks = el('div');
      for (const test of req.tests || []) checks.append(el('pre', 'mica-code', test.call + ' → ' + JSON.stringify(test.expected)));
      ui.proposal.append(details(task.kind === 'objective' ? 'Proposed acceptance examples' : 'Supplied acceptance examples', checks));
    }
    if (task.kind === 'forge') {
      const source = section('Frozen Forge source', 'The original handoff and accepted unit mapping are retained. Building does not accept or replace Forge requirements.');
      const origin = task.prepared?.origin || {};
      source.append(el('p', 'mica-hash', 'Project ' + (origin.project || '') + ' · Handoff ' + (origin.handoff || '')),
        el('pre', 'mica-code', JSON.stringify({accepted: origin.accepted_authority, finite_bindings: task.prepared?.criterion_mapping,
          semantic_completeness: result.semantic_completeness || 'unassessed'}, null, 2)));
      ui.proposal.append(details('Accepted source and executable bindings', source));
    }
    const missing = result.missing_decisions || [];
    if (missing.length) {
      const decisions = section('Decisions needed', 'Revise the objective to resolve these choices before creating a new plan.');
      for (const row of missing) { decisions.append(el('p', 'mica-note', row.question), el('p', 'mica-note', row.why_consequential)); }
      ui.proposal.append(decisions);
    }
    const plan = result.plan || result.child?.plan || task.prepared?.plan;
    if (plan?.contracts) {
      const graph = el('ol', 'mica-list');
      for (const contract of plan.contracts) {
        const deps = contract.dependency_contract_ids || [];
        graph.append(el('li', '', (contract.contract_id || '') + ' — ' + (contract.objective || '') +
          (deps.length ? ' Uses: ' + deps.join(', ') + '.' : ' No dependencies.')));
      }
      ui.proposal.append(details('Construction plan · ' + plan.contracts.length + ' units', graph));
    }
    const provenance = result.provenance || {};
    const evidence = el('div');
    evidence.append(el('p', 'mica-note', provenance.scope || value.scope || 'Finite encoded checks do not establish universal correctness.'));
    const sources = el('dl', 'mica-note');
    for (const [label, text] of [['Objective', provenance.objective || 'caller'],
      ['Requirements', provenance.requirements || (task.kind === 'forge' ? 'accepted Forge source and explicit finite bindings' : task.kind === 'request' ? 'caller' : 'not yet proposed')],
      ['Assumptions', provenance.assumptions || (task.kind === 'forge' ? 'accepted Forge source and explicit finite bindings' : task.kind === 'request' ? 'caller' : 'not yet proposed')],
      ['Acceptance tests', provenance.acceptance_tests || (task.kind === 'forge' ? 'accepted Forge source and explicit finite bindings' : task.kind === 'request' ? 'caller' : 'not yet proposed')],
      ['Assurance', result.assurance || 'No accepted artifact']]) {
      sources.append(el('dt', '', label), el('dd', '', text));
    }
    evidence.append(sources, el('pre', 'mica-code', JSON.stringify({original_budget: budget, costs: result.costs || null,
      measurements: result.measurements || null, host_costs: result.host_costs || null, request_sha256: result.request_sha256 || null,
      deadline_ms: result.evidence?.deadline_ms || null, audit_scope: value.audit_scope || null}, null, 2)));
    ui.proposal.append(details('Provenance, original budget and measurements', evidence));
    ui.artifactsButton.disabled = value.status !== 'done';
    setControls();
  }
  function schedule(g) {
    clearTimeout(timer);
    if (alive(g) && selected) timer = setTimeout(() => refresh(g), 5000);
  }
  async function refresh(g = generation) {
    if (!alive(g) || !selected || reading || ui.busy) return;
    reading = true; const id = selected, epoch = statusEpoch;
    try {
      const value = await api('run?id=' + encodeURIComponent(id));
      if (alive(g) && id === selected && epoch === statusEpoch) { showCurrent(value); note('Status updated. Observation does not spend model calls.'); }
    } catch (error) {
      if (alive(g) && error.name !== 'AbortError') note((pendingLaunch ?
        'Launch outcome is unknown. Keep this run ID; refresh only checks its record. ' : 'Status could not be read. ') + error.message, true);
    } finally { reading = false; schedule(g); }
  }
  async function history(g = generation) {
    try {
      const value = await api('runs'); if (!alive(g)) return;
      ui.history.replaceChildren();
      for (const row of value.runs || []) {
        if (!ID.test(row.id)) continue;
        const line = el('div', 'mica-run-row');
        line.append(el('p', 'mica-note', (row.title || row.id) + ' · ' + (row.status || 'unknown')),
          button('Read run ' + row.id, () => select(row.id), 'ghost'));
        ui.history.append(line);
      }
      if (!ui.history.childElementCount) ui.history.append(el('p', 'mica-note', 'No construction runs yet.'));
    } catch (error) { if (alive(g) && error.name !== 'AbortError') ui.history.textContent = error.message; }
  }
  function select(id) {
    if (!ui || !ID.test(id) || ui.busy || pendingLaunch) return;
    statusEpoch++; save(id); current = null; ui.artifacts.replaceChildren(); ui.run.hidden = false;
    ui.runTitle.textContent = 'Reading retained run…'; ui.runId.textContent = 'Run ' + id; setControls(); refresh();
  }
  async function control(action) {
    if (!ui || ui.busy || !selected) return;
    const permitted = action === 'execute' ? current?.can_execute : action === 'resume' ? current?.can_resume : current?.active;
    if (permitted !== true || (action === 'resume' && current?.status === 'unknown') ||
      (action === 'execute' && current?.status !== 'planned')) return;
    const g = generation, id = selected; statusEpoch++; ui.busy = true; setControls();
    try {
      await api(action, {id});
      if (alive(g)) note(action === 'stop' ? 'Stop requested. Waiting for the worker’s recorded state.' : 'Request recorded. Reading status.');
    } catch (error) { if (alive(g)) note('The control request has an uncertain outcome. Refresh status before another action. ' + error.message, true); }
    finally { if (alive(g)) { ui.busy = false; current = null; setControls(); refresh(g); } }
  }
  async function launchPlan() {
    if (!ui || ui.plan.disabled || !ui.form.reportValidity()) return;
    const g = generation;
    const chosen = ui.workers.filter(row => row.input.checked && !row.input.disabled).map(row => row.value);
    if (!chosen.length) { note('Choose at least one available fleet worker.', true); return; }
    let body;
    if (ui.source.value === 'forge') {
      try {
        body = {forge: {project: ui.forgeProject.value.trim(), handoff: ui.forgeHandoff.value.trim(),
          binding: JSON.parse(ui.forgeBinding.value)}, inventory: chosen, mode: 'mica'};
      } catch (_) { note('Executable bindings must be valid JSON.', true); return; }
    } else {
      body = {objective: ui.objective.value.trim(), allowed_outputs: [ui.output.value.trim()], inventory: chosen,
        artifact_format: ui.format.value,
        budget: Object.fromEntries(Object.entries(ui.budgets).map(([key, input]) => [key, Number(input.value)])),
        mode: ui.mode.value, reuse_components: ui.reuse.checked};
    }
    statusEpoch++; ui.busy = true; setControls();
    try {
      const checked = await api('check', body); if (!alive(g)) return;
      const key = 'construct-' + crypto.randomUUID();
      const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key));
      if (!alive(g)) return;
      const id = Array.from(new Uint8Array(bytes), n => n.toString(16).padStart(2, '0')).join('').slice(0, 12);
      save(id, true); current = null; ui.artifacts.replaceChildren();
      ui.run.hidden = false; ui.runTitle.textContent = 'Planning request'; ui.runId.textContent = 'Run ' + id;
      note(body.forge ? 'Validating the fixed Forge plan. Execution will retain its original budget and unit mapping.' : 'Planning requested. It uses the original shared call and time budget.');
      const value = await api('plan', {...body, expected_sha256: checked.sha256, idempotency_key: key});
      if (value.id !== id) throw new Error('Returned run identity differs from the reserved request.');
      if (alive(g)) { save(id, false); await history(g); }
    } catch (error) {
      // Only a definite rejection followed by an authoritative absent record permits revision.
      // Transport failures, 503s and unreadable records remain unresolved and non-replayed.
      if (alive(g) && pendingLaunch && [400, 403, 409].includes(error.status)) {
        const id = selected;
        try {
          const retained = await api('run?id=' + encodeURIComponent(id));
          if (alive(g) && id === selected) { showCurrent(retained); note('The existing run was retained. ' + error.message, true); return; }
        } catch (observation) {
          if (alive(g) && id === selected && observation.status === 404) {
            save('', false); current = null; ui.run.hidden = true;
            note('The plan was rejected and no job record exists. Revise the objective or availability, then propose again. ' + error.message, true); return;
          }
        }
      }
      if (alive(g)) note((pendingLaunch ? 'Launch outcome is unknown. Refresh checks the retained ID without sending again. ' : '') + error.message, true);
    } finally { if (alive(g)) { ui.busy = false; setControls(); refresh(g); } }
  }
  async function artifacts() {
    if (!ui || !selected || current?.status !== 'done') return;
    const g = generation, id = selected; ui.artifactsButton.disabled = true;
    try {
      const modules = current.result?.bundle || current.spec?.task?.artifact_format === 'javascript_modules' ||
        current.spec?.task?.request?.artifact_format === 'javascript_modules';
      const value = await api('artifacts?id=' + encodeURIComponent(id) + '&text=1' + (modules ? '&archive=1' : ''));
      if (!alive(g) || id !== selected) return;
      ui.artifacts.replaceChildren();
      if (typeof value.archive?.base64 === 'string' && value.archive.base64.length <= 1500000) {
        const archive = value.archive;
        ui.artifacts.append(button('Download module bundle', () => {
          const bytes = Uint8Array.from(atob(archive.base64), c => c.charCodeAt(0));
          const url = URL.createObjectURL(new Blob([bytes], {type: 'application/zip'}));
          const a = el('a'); a.href = url; a.download = 'symblic-modules.zip';
          a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        }), el('p', 'mica-note', 'The ZIP preserves module directories and relative imports.'));
      }
      for (const row of value.artifacts || []) {
        if (typeof row.text !== 'string') continue;
        const part = section(row.file || 'Artifact');
        part.append(el('p', 'mica-hash', 'SHA-256 ' + (row.sha256 || 'unknown')),
          el('p', 'mica-note', number(row.bytes) + ' bytes · ' + (row.assurance || 'See run assurance')));
        part.append(button('Download ' + (row.file || 'artifact'), () => {
          const url = URL.createObjectURL(new Blob([row.text], {type: 'text/javascript;charset=utf-8'}));
          const a = el('a'); a.href = url; a.download = String(row.file || 'result.js').split('/').pop();
          a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        }), details('View source', el('pre', 'mica-code', row.text)));
        ui.artifacts.append(part);
      }
      if (!ui.artifacts.childElementCount) ui.artifacts.textContent = 'No accepted artifact is recorded.';
    } catch (error) { if (alive(g)) note('Artifact could not be read. ' + error.message, true); }
    finally { if (alive(g)) ui.artifactsButton.disabled = current?.status !== 'done'; }
  }
  async function ready(g) {
    try {
      const [cap, fleet] = await Promise.all([api('capabilities'), api('inventory')]);
      if (!alive(g)) return;
      if (cap.version !== 1 || !Array.isArray(fleet.inventory)) throw new Error('Construction service returned an unsupported response.');
      for (const [key, input] of Object.entries(ui.budgets)) {
        if (!Number.isInteger(cap.budget_defaults?.[key])) throw new Error('Construction budget defaults are unavailable.');
        const bounds = cap.budget_limits?.[key];
        if (Array.isArray(bounds) && bounds.length === 2 && bounds.every(Number.isInteger)) { input.min = bounds[0]; input.max = bounds[1]; }
        if (!ui.initialized) input.value = cap.budget_defaults[key];
      }
      ui.forgeChoice.disabled = !(cap.task_sources || []).includes('forge');
      if (ui.source.value === 'forge' && ui.forgeChoice.disabled) { ui.source.value = 'objective'; changeSource(); }
      const previousMode = ui.mode.value;
      const previousWorkers = new Map(ui.workers.map(row => [JSON.stringify([row.value.engine, row.value.model, row.value.node]), row.input.checked]));
      ui.mode.replaceChildren();
      for (const mode of cap.modes || []) { const choice = el('option', '', mode === 'mica' ? 'Adaptive construction' : mode.replaceAll('_', ' ')); choice.value = mode; ui.mode.append(choice); }
      ui.mode.value = cap.modes.includes(previousMode) ? previousMode : 'mica';
      ui.workerList.replaceChildren(); ui.workers = [];
      for (const row of fleet.inventory) {
        const label = el('label', 'mica-worker'), input = el('input'); input.type = 'checkbox';
        input.disabled = row.ready !== true || row.available !== true;
        input.checked = !input.disabled && (previousWorkers.get(JSON.stringify([row.engine, row.model, row.node])) ?? true);
        const text = el('span', '', String(row.model || '') + ' · ' + String(row.node || ''));
        text.append(el('small', '', input.disabled ? 'Unavailable in this snapshot' : 'Available in this snapshot; admission is checked at launch'));
        label.append(input, text); ui.workerList.append(label); ui.workers.push({input, value: row});
      }
      if (!ui.workers.length) ui.workerList.append(el('p', 'mica-note', 'No fleet workers are available. Refresh the snapshot before planning.'));
      ui.fleetNote.textContent = (fleet.scope || 'This discovery snapshot does not reserve a worker.') + ' Availability is cached. Refresh workers checks online fleet nodes and their model catalogues.';
      if (fleet.observed_at) ui.fleetNote.textContent += ' Observed: ' + String(fleet.observed_at);
      if ((fleet.diagnostics || []).length) ui.fleetNote.textContent += ' ' + fleet.diagnostics.map(row => typeof row === 'string' ? row : JSON.stringify(row)).join(' ');
      ui.initialized = true; ui.ready = true; setControls();
      if (!selected) note('Ready to propose a plan. Planning and execution share one original budget.');
    } catch (error) {
      if (!alive(g) || error.name === 'AbortError') return;
      ui.ready = false; setControls(); note(error.message + ' Refresh workers to check again; nothing was launched.', true);
    }
  }
  async function refreshWorkers(g = generation) {
    if (!alive(g) || ui.busy || ui.refreshing || pendingLaunch) return;
    ui.refreshing = true; setControls(); note('Checking online workers and their model catalogues…');
    try {
      const state = await request('/api/cluster/status?force=1');
      if (!alive(g)) return;
      if (!Array.isArray(state.status)) throw new Error('Fleet readiness returned an unsupported response.');
      // Worker machines are the rows the host's fleet status tags 'worker' (the original host used its own
      // hardware tag here); change the tag to match your fleet's status API.
      const ids = [...new Set(state.status.filter(row => row.online === true && !row.local && !row.swarmHost &&
        row.role !== 'cloud' && Array.isArray(row.tags) && row.tags.includes('worker') &&
        typeof row.id === 'string' && /^[a-zA-Z0-9_-]{1,80}$/.test(row.id)).map(row => row.id))].sort();
      if (ids.length > 32) throw new Error('This fleet exceeds the bounded refresh size. Use Agents to refresh selected nodes.');
      let next = 0; const failures = [];
      async function worker() {
        while (alive(g) && next < ids.length) {
          const node = ids[next++];
          try { await request('/api/fleet/probe', {node}, true); }
          catch (error) {
            if (!alive(g) || error.name === 'AbortError') return;
            failures.push(node + ': ' + error.message);
          }
        }
      }
      await Promise.all([worker(), worker()]);
      if (!alive(g)) return;
      await ready(g);
      if (alive(g) && ui.ready) note(failures.length ? 'Some worker checks failed. ' + failures.join(' ') :
        'Worker checks finished. Planning still requires its own explicit action.', failures.length > 0);
    } catch (error) {
      if (alive(g) && error.name !== 'AbortError') note('Worker availability could not be refreshed. ' + error.message, true);
    } finally { if (alive(g)) { ui.refreshing = false; setControls(); } }
  }
  function changeSource() {
    if (!ui) return;
    const forge = ui.source.value === 'forge';
    ui.objectiveFields.hidden = forge; ui.forgeFields.hidden = !forge;
    for (const input of ui.objectiveFields.querySelectorAll('input,textarea,select')) input.disabled = forge;
    for (const input of ui.forgeFields.querySelectorAll('input,textarea')) input.disabled = !forge;
    ui.plan.textContent = forge ? 'Validate frozen plan' : 'Propose plan';
  }
  function stop() {
    generation++; statusEpoch++; clearTimeout(timer); timer = null;
    for (const controller of controllers) controller.abort(); controllers.clear();
    reading = false; ui = null;
  }
  function render(mount) {
    stop(); const g = generation; restore(); current = null;
    const root = el('div', 'mica'); mount.replaceChildren(root);
    const intro = section('Construct', 'Turn an objective into a plan and checked JavaScript components.');
    intro.append(el('p', 'mica-lead', 'Describe the behavior you need. Inspect the proposed requirements and assumptions, then build within one shared budget.'));
    root.append(intro);
    const message = el('p', 'mica-note mica-message', 'Reading construction availability…'); message.setAttribute('role', 'status'); message.setAttribute('aria-live', 'polite'); root.append(message);
    const draft = section('New construction'); const form = el('form', 'mica-form'); form.addEventListener('submit', event => event.preventDefault());
    const objective = el('textarea', 'field'); objective.required = true; objective.maxLength = 12000; objective.rows = 5;
    objective.placeholder = 'Build a Markdown renderer with headings, lists and inline emphasis. State how unsupported syntax should behave.';
    const source = el('select', 'field');
    const objectiveChoice = el('option', '', 'New objective'); objectiveChoice.value = 'objective';
    const forgeChoice = el('option', '', 'Accepted Forge handoff'); forgeChoice.value = 'forge'; forgeChoice.disabled = true;
    source.append(objectiveChoice, forgeChoice); source.addEventListener('change', changeSource);
    form.append(field('Construction source', source));
    const objectiveFields = el('div', 'mica-form'); objectiveFields.append(field('Objective', objective));
    const forgeFields = el('div', 'mica-form'); forgeFields.hidden = true;
    const forgeProject = el('input', 'field'), forgeHandoff = el('input', 'field'), forgeBinding = el('textarea', 'field');
    for (const input of [forgeProject, forgeHandoff]) { input.required = true; input.maxLength = 100; input.pattern = '[A-Za-z0-9_-]{8,100}'; }
    forgeBinding.required = true; forgeBinding.maxLength = 200000; forgeBinding.rows = 10;
    forgeBinding.placeholder = 'Paste the explicit executable binding JSON for this frozen handoff.';
    forgeFields.append(el('p', 'mica-note', 'Use an accepted pure-function Forge handoff and explicit executable bindings. Its budget, units, output format and tests stay fixed.'),
      field('Forge project ID', forgeProject), field('Frozen handoff ID', forgeHandoff), field('Executable bindings JSON', forgeBinding));
    form.append(objectiveFields, forgeFields);
    const budgetMain = el('div', 'mica-grid'), budgets = {};
    const fields = [['max_calls', 'Total model calls', 0, 10000], ['wall_seconds', 'Total time (seconds)', 1, 86400],
      ['max_candidates', 'Alternative plans', 1, 32], ['max_depth', 'Decomposition depth', 1, 16],
      ['max_units', 'Maximum units', 1, 128], ['max_workers', 'Parallel workers', 1, 8],
      ['retries', 'Repairs per unit', 0, 8], ['context_chars', 'Context characters', 256, 262144]];
    const advanced = el('div', 'mica-grid');
    for (const [key, title, min, max] of fields) {
      const input = el('input', 'field'); input.type = 'number'; input.min = min; input.max = max; input.step = 1; input.required = true;
      budgets[key] = input; (['max_calls', 'wall_seconds'].includes(key) ? budgetMain : advanced).append(field(title, input));
    }
    objectiveFields.append(budgetMain, el('p', 'mica-note', 'The deadline starts with planning. Execute and resume retain the original budget; they do not reset it.'));
    const output = el('input', 'field'); output.value = 'result.js'; output.required = true; output.maxLength = 240;
    const format = el('select', 'field');
    for (const [value, title] of [['javascript_script', 'One JavaScript file'], ['javascript_modules', 'JavaScript module bundle']]) {
      const option = el('option', '', title); option.value = value; format.append(option);
    }
    const mode = el('select', 'field'); advanced.append(field('Output format', format), field('Output file or module entry', output), field('Construction strategy', mode));
    const reuse = el('input'); reuse.type = 'checkbox'; const reuseLabel = el('label', 'mica-worker');
    reuseLabel.append(reuse, el('span', '', 'Reuse retained components after checking them again'));
    advanced.append(reuseLabel); objectiveFields.append(details('Advanced limits and reuse', advanced));
    const workerList = el('div', 'mica-workers'), fleetNote = el('p', 'mica-note');
    const workersPanel = el('div'); workersPanel.append(workerList, fleetNote);
    form.append(details('Eligible fleet workers', workersPanel));
    const plan = button('Propose plan', launchPlan, 'acc'); plan.disabled = true;
    const refreshWorkersButton = button('Refresh workers', () => refreshWorkers(g), 'ghost');
    form.append(el('div', 'mica-actions')); form.lastChild.append(plan, refreshWorkersButton);
    draft.append(form); root.append(draft);
    const run = section('Retained run'); run.hidden = !selected;
    const runTitle = el('h3', '', selected ? 'Reading retained run…' : ''), runId = el('p', 'mica-hash', selected ? 'Run ' + selected : '');
    const stats = el('div', 'mica-status'), runMessage = el('p', 'mica-note mica-message'), actions = el('div', 'mica-actions');
    const execute = button('Execute plan', () => control('execute'), 'acc'), resume = button('Resume explicitly', () => control('resume')),
      halt = button('Stop run', () => control('stop'), 'danger');
    actions.append(execute, resume, halt, button('Refresh status', () => refresh(), 'ghost'));
    run.append(runTitle, runId, stats, runMessage, actions); root.append(run);
    const proposal = el('div'), artifactSection = section('Artifacts', 'Accepted source can be inspected or downloaded. It is not executed in this page.'),
      artifactsButton = button('Read artifacts', artifacts), artifactList = el('div');
    artifactSection.append(artifactsButton, artifactList); root.append(proposal, artifactSection);
    const past = section('Recent runs', 'Opening a run only reads its retained status.'); const historyList = el('div');
    past.append(button('Refresh runs', () => history(g), 'ghost'), historyList); root.append(past);
    ui = {root, message, ready: false, busy: false, form, objective, budgets, output, format, mode, reuse, workers: [],
      source, forgeChoice, objectiveFields, forgeFields, forgeProject, forgeHandoff, forgeBinding,
      workerList, fleetNote, plan, refreshWorkers: refreshWorkersButton, refreshing: false, run, runTitle, runId, stats, runMessage, execute, resume, stop: halt,
      proposal, artifactsButton, artifacts: artifactList, history: historyList};
    changeSource(); setControls(); artifactsButton.disabled = true;
    ready(g); history(g); if (selected) refresh(g);
  }
  window.addEventListener('online', () => { if (ui && selected) refresh(); });
  window.SymblicMica = {render, stop};
})();
