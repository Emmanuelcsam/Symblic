/* Bounded graph drafts and durable run receipts. Model/effect dispatch is server-owned. */
(function () {
  'use strict';
  const API = '/api/automation/symblic/graph/', KEY = 'symblic-graph-draft-v1', LIMIT = 1048576;
  const COMPOSITION_KEY = 'symblic-graph-composition-v1', SESSION_LIMIT = 4 * LIMIT;
  const bytes = text => new TextEncoder().encode(text).length;
  const NUMBER_GUIDANCE = 'This browser accepts JSON integer literals only from -9007199254740991 to 9007199254740991. Keep the original file and use bin/symblic graph compose FILE.json --flat for larger exact integers. Fractional and exponent-form JSON numbers are unsupported by graph contracts.';
  function checkNumberText(raw) {
    // A monotonic cursor skips quoted data, including unterminated strings,
    // without retrying at escaped quotes. JSON.parse remains syntax authority.
    const digit = char => char >= '0' && char <= '9';
    for (let i = 0; i < raw.length;) {
      const char = raw[i++];
      if (char === '"') {
        while (i < raw.length) {
          const quoted = raw[i++];
          if (quoted === '\\') { if (i < raw.length) i++; }
          else if (quoted === '"') break;
        }
      } else if (digit(char) || (char === '-' && digit(raw[i]))) {
        const start = i - 1;
        // Conversion only sees a bounded integer token. Fraction/exponent
        // notation is refused because the native graph contract rejects floats.
        while (i < raw.length && digit(raw[i])) {
          if (++i - start > 17) throw new Error(NUMBER_GUIDANCE);
        }
        if (raw[i] === '.' || raw[i] === 'e' || raw[i] === 'E' ||
            !Number.isSafeInteger(Number(raw.slice(start, i)))) {
          throw new Error(NUMBER_GUIDANCE);
        }
      }
    }
  }
  function checkResponseNumbers(value) {
    // Studio.api has already decoded JSON. Every integer outside the safe range
    // is rejected here before adoption; lost lexemes cannot be reconstructed.
    let count = 0, textBytes = 0;
    function visit(item, depth) {
      if (++count > 50000 || depth > 24) throw new Error('The graph response exceeds the browser authoring structure limit.');
      if (typeof item === 'number' && !Number.isSafeInteger(item)) throw new Error(NUMBER_GUIDANCE);
      if (typeof item === 'string') {
        textBytes += bytes(item);
        if (textBytes > SESSION_LIMIT) throw new Error('The graph response exceeds the browser authoring byte limit.');
      } else if (Array.isArray(item)) {
        for (const child of item) visit(child, depth + 1);
      } else if (item && typeof item === 'object') {
        for (const [key, child] of Object.entries(item)) {visit(key, depth + 1); visit(child, depth + 1);}
      }
    }
    visit(value, 0);
  }
  const vm = { raw: '', selected: '', description: '', checked: null, revision: 0, busy: '', error: '',
    listError: '', runError: '', notice: '', runs: [], run: null, advanced: false, receipts: false,
    mount: null, view: null, timer: null, reading: 0, listing: 0, checking: 0, loadingExample: false, nodePage: 0, epoch: 0,
    composition: '', compositionRevision: 0, compositionTicket: 0, compositionBusy: '',
    compositionError: '', compositionNotice: '', compositionOpen: false, compositionReceipt: null };
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    if (saved && typeof saved.raw === 'string' && saved.raw.length <= LIMIT) vm.raw = saved.raw;
    if (saved && typeof saved.selected === 'string') vm.selected = saved.selected.slice(0, 128);
  } catch (_) { }
  try {
    const raw = sessionStorage.getItem(COMPOSITION_KEY) || 'null';
    if (bytes(raw) <= SESSION_LIMIT) {
      const saved = JSON.parse(raw);
      if (saved && typeof saved.raw === 'string' && bytes(saved.raw) <= LIMIT) vm.composition = saved.raw;
      const receipt = saved?.receipt;
      if (receipt && typeof receipt.source === 'string' && bytes(receipt.source) <= LIMIT &&
          typeof receipt.flat === 'string' && bytes(receipt.flat) <= LIMIT && receipt.response?.manifest) {
        vm.compositionReceipt = {...receipt, restored:true};
      }
    }
  } catch (_) { }
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === 'text') node.textContent = value;
      else if (key === 'class') node.className = value;
      else if (key === 'on') Object.entries(value).forEach(([event, fn]) => node.addEventListener(event, fn));
      else if (['value', 'disabled', 'open'].includes(key)) node[key] = value;
      else node.setAttribute(key, value);
    });
    children.flat().forEach(child => node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child));
    return node;
  }
  const visible = () => vm.view && vm.view.isConnected && vm.view.parentElement === vm.mount;
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify({raw: vm.raw, selected: vm.selected})); } catch (_) { } }
  function saveComposition() {
    try {
      if (bytes(vm.composition) > LIMIT) throw new Error('Composition drafts are limited to 1 MiB.');
      const raw = JSON.stringify({raw:vm.composition, receipt:vm.compositionReceipt});
      if (bytes(raw) > SESSION_LIMIT) throw new Error('This expansion is too large for session retention. Keep a separate copy before leaving.');
      sessionStorage.setItem(COMPOSITION_KEY, raw);
    } catch (error) { vm.compositionNotice = error.message || 'This browser could not retain the composition in this session.'; }
  }
  function message(error) { return error.status === 503 ? 'Graph execution is unavailable on this server. ' + error.message : error.message || 'The graph request failed.'; }
  function parse() {
    if (new TextEncoder().encode(vm.raw).length > LIMIT) throw new Error('Graph documents are limited to 1 MiB.');
    checkNumberText(vm.raw);
    let value;
    try { value = JSON.parse(vm.raw); } catch (_) { throw new Error('The graph document must be valid JSON containing graph and policy.'); }
    if (!value || Array.isArray(value) || typeof value !== 'object' || !value.graph || !value.policy ||
        Object.keys(value).some(key => !['graph', 'policy'].includes(key))) {
      throw new Error('Use a JSON object with exactly graph and policy.');
    }
    return value;
  }
  function change(raw) {
    vm.raw = raw; vm.revision++; vm.checked = null; vm.checking++; vm.error = ''; vm.notice = ''; save();
    const editor = visible() && vm.view.querySelector('#sy-graph-json');
    if (editor && editor.value !== raw) editor.value = raw;
    paintControls(); paintOverview(); paintComposition();
  }
  function compositionDocument(raw) {
    if (bytes(raw) > LIMIT) throw new Error('Composition documents are limited to 1 MiB.');
    checkNumberText(raw);
    let value;
    try { value = JSON.parse(raw); } catch (_) { throw new Error('The composition document must be valid JSON containing composition and policy.'); }
    if (!value || Array.isArray(value) || typeof value !== 'object' ||
        !value.composition || typeof value.composition !== 'object' || Array.isArray(value.composition) ||
        !value.policy || typeof value.policy !== 'object' || Array.isArray(value.policy) ||
        Object.keys(value).length !== 2) throw new Error('Use a JSON object with exactly composition and policy.');
    return value;
  }
  function changeComposition(raw) {
    vm.composition = raw; vm.compositionRevision++; vm.compositionError = ''; vm.compositionNotice = '';
    saveComposition(); paintComposition();
  }
  async function compositionAction(kind) {
    if (vm.busy || vm.compositionBusy) return;
    const ticket = ++vm.compositionTicket, revision = vm.revision, compositionRevision = vm.compositionRevision,
      epoch = vm.epoch, view = vm.view, source = vm.composition;
    const mounted = () => ticket === vm.compositionTicket && epoch === vm.epoch && view === vm.view && visible();
    const current = () => mounted() && revision === vm.revision && compositionRevision === vm.compositionRevision;
    vm.compositionBusy = kind; vm.compositionError = ''; vm.compositionNotice = ''; paintControls(); paintComposition();
    try {
      const response = kind === 'example' ? await Studio.api(API + 'composition-example') :
        await Studio.api(API + 'compose', compositionDocument(source));
      if (!current()) {
        if (mounted()) vm.compositionNotice = 'The draft changed while the request was pending. Its response was not applied.';
        return;
      }
      checkResponseNumbers(response);
      if (kind === 'example') {
        const raw = JSON.stringify(response, null, 2);
        compositionDocument(raw); changeComposition(raw);
        const editor = vm.view.querySelector('#sy-graph-composition'); if (editor) editor.value = vm.composition;
        vm.compositionNotice = 'Reusable example loaded into the composition editor. The flat draft is unchanged.';
      } else {
        if (!response || response.ok !== true || response.version !== 1 || !response.draft ||
            !response.draft.graph || !response.draft.policy || Object.keys(response.draft).length !== 2 ||
            !Array.isArray(response.draft.graph.nodes) || !response.manifest || !response.check ||
            response.check.ok !== true || typeof response.check.graph_hash !== 'string' ||
            typeof response.check.policy_hash !== 'string' ||
            response.manifest.graph_hash !== response.check.graph_hash ||
            response.manifest.policy_hash !== response.check.policy_hash) {
          throw new Error('The server returned an incomplete composition expansion. Both drafts were preserved.');
        }
        const raw = JSON.stringify(response.draft, null, 2);
        if (bytes(raw) > LIMIT || bytes(JSON.stringify(response)) > SESSION_LIMIT) throw new Error('The expanded draft or receipt exceeds the browser authoring limit. Both drafts were preserved.');
        // This explicit authoring action adopts only the flat draft. The server's
        // admission receipt is retained for review, never installed as vm.checked.
        change(raw); vm.description = ''; vm.advanced = true;
        vm.compositionReceipt = {source, flat:raw, response, restored:false};
        vm.compositionNotice = 'Expanded into the flat draft. Check graph before running; expansion does not start a run.';
        const editor = vm.view.querySelector('#sy-graph-json'); if (editor) editor.value = raw;
        const advanced = vm.view.querySelector('[data-graph-advanced]'); if (advanced) advanced.open = true;
      }
      saveComposition();
    } catch (error) {
      if (current()) vm.compositionError = error.status === 503 || error.status === 404 ?
        'Graph composition is unavailable on this server. ' + (error.message || '') : error.message || 'The composition request failed.';
    } finally {
      if (ticket === vm.compositionTicket) {vm.compositionBusy = ''; paintControls(); paintOverview(); paintComposition();}
    }
  }
  function paintComposition() {
    if (!visible()) return;
    const controls = vm.view.querySelector('[data-composition-controls]'), receiptView = vm.view.querySelector('[data-composition-receipt]');
    if (!controls || !receiptView) return;
    const busy = !!vm.busy || !!vm.compositionBusy;
    controls.replaceChildren(el('div', {class:'sy-graph-actions'},
      el('button', {class:'btn', text:vm.compositionBusy === 'example' ? 'Loading reusable example…' : 'Load reusable example', disabled:busy,
        on:{click:()=>compositionAction('example')}}),
      el('button', {class:'btn', text:vm.compositionBusy === 'expand' ? 'Expanding…' : 'Expand to flat draft', disabled:busy || !vm.composition.trim(),
        on:{click:()=>compositionAction('expand')}})));
    if (vm.compositionError) controls.appendChild(el('p', {role:'alert', class:'sy-graph-error', text:vm.compositionError}));
    if (vm.compositionNotice) controls.appendChild(el('p', {role:'status', text:vm.compositionNotice}));
    receiptView.replaceChildren();
    const receipt = vm.compositionReceipt; if (!receipt) return;
    const matches = receipt.source === vm.composition && receipt.flat === vm.raw;
    const label = !matches ? 'Detached authoring receipt: a draft has changed since this expansion.' :
      receipt.restored ? 'Restored authoring receipt for these drafts; it does not restore execution approval.' :
        'Authoring receipt matches these drafts; it is not execution approval.';
    receiptView.appendChild(el('p', {'data-composition-status':'', role:'status', class:'hint', text:label}));
    const check = receipt.response.check;
    if (check) receiptView.appendChild(el('p', {text:'Expansion recorded ' + check.nodes + ' leaves · ' + check.iterations +
      ' parent iteration(s) · shared limit ' + check.max_calls + ' reserved calls.'}));
    receiptView.appendChild(jsonDetails('Composition source, mapping and expansion receipt',
      {composition_source:receipt.source, expansion:receipt.response}));
  }
  async function example() {
    if (vm.busy || vm.loadingExample) return;
    const revision = vm.revision;
    vm.loadingExample = true; vm.busy = 'example'; vm.error = ''; paintControls();
    try {
      const value = await Studio.api(API + 'example');
      checkResponseNumbers(value);
      if (!value.graph || !value.policy) throw new Error('The example response is incomplete.');
      // An example read must never overwrite a draft edited while the request was pending.
      if (revision === vm.revision) {
        vm.description = value.description || ''; change(JSON.stringify({graph:value.graph, policy:value.policy}, null, 2));
        const editor = visible() && vm.view.querySelector('#sy-graph-json'); if (editor) editor.value = vm.raw;
      }
    } catch (error) { vm.error = message(error); }
    finally { vm.loadingExample = false; vm.busy = ''; paintControls(); paintOverview(); }
  }
  async function check() {
    if (vm.busy) return;
    const revision = vm.revision, ticket = ++vm.checking;
    vm.checked = null; vm.error = ''; vm.notice = ''; vm.busy = 'check'; paintControls();
    try {
      const document = parse(), response = await Studio.api(API + 'check', document);
      if (!response.ok || typeof response.graph_hash !== 'string' || typeof response.policy_hash !== 'string') {
        throw new Error('The server returned an incomplete graph check.');
      }
      if (revision === vm.revision && ticket === vm.checking) vm.checked = {revision, document, response};
    } catch (error) { if (ticket === vm.checking) vm.error = message(error); }
    finally { vm.busy = ''; paintControls(); }
  }
  async function run() {
    if (vm.busy || !vm.checked || vm.checked.revision !== vm.revision) return;
    const checked = vm.checked;
    vm.busy = 'run'; vm.error = ''; vm.notice = ''; paintControls();
    try {
      const result = await Studio.api(API + 'run', {...checked.document,
        expected_graph_hash: checked.response.graph_hash, expected_policy_hash: checked.response.policy_hash});
      if (!result.id || typeof result.id !== 'string') throw new Error('The server did not return a saved run ID.');
      vm.selected = result.id; vm.run = null; vm.receipts = false; vm.nodePage = 0; save();
      vm.notice = 'Run saved. Inspect its recorded status below.';
      await Promise.all([readRun(result.id), refreshRuns()]);
    } catch (error) {
      vm.checked = null;
      vm.error = message(error) + (error.status === 409 ? ' Check the current document again.' : ' Inspect saved runs before submitting again; this request will not be retried automatically.');
    } finally { vm.busy = ''; paintControls(); paintRun(); }
  }
  async function refreshRuns() {
    const ticket = ++vm.listing;
    try {
      const value = await Studio.api(API + 'runs');
      if (!Array.isArray(value.runs)) throw new Error('The saved graph run list is unavailable.');
      if (ticket !== vm.listing) return;
      vm.runs = value.runs; vm.listError = '';
    } catch (error) { if (ticket !== vm.listing) return; vm.listError = message(error); }
    paintRuns();
  }
  function schedule() {
    clearTimeout(vm.timer);
    if (!visible() || !vm.run || (!vm.run.active && vm.run.state.status !== 'starting') || !vm.selected) return;
    const id = vm.selected;
    vm.timer = setTimeout(() => { if (visible() && vm.selected === id) readRun(id); }, 1800);
  }
  async function readRun(id) {
    const ticket = ++vm.reading;
    try {
      const value = await Studio.api(API + 'run?id=' + encodeURIComponent(id));
      if (value.id !== id || !value.state) throw new Error('The server returned an incomplete graph run.');
      if (vm.selected !== id || ticket !== vm.reading) return;
      vm.run = value; vm.runError = '';
    } catch (error) { if (vm.selected === id && ticket === vm.reading) vm.runError = message(error); }
    if (vm.selected !== id || ticket !== vm.reading) return;
    paintRun(); schedule();
  }
  async function control(action) {
    if (vm.busy || !vm.selected || !vm.run) return;
    const id = vm.selected;
    vm.busy = action; vm.runError = ''; paintRun(); paintControls();
    try {
      await Studio.api(API + action, {id});
      if (id === vm.selected) await readRun(id);
      await refreshRuns();
    } catch (error) { if (id === vm.selected) vm.runError = message(error); }
    finally { vm.busy = ''; paintRun(); paintControls(); }
  }
  function jsonDetails(title, value, attrs = {}) {
    const pre = el('pre', {tabindex: '0', 'aria-label': title});
    const details = el('details', {...attrs, on:{toggle: e => {
      if (e.target.open && !pre.textContent) pre.textContent = JSON.stringify(value, null, 2);
    }}}, el('summary', {text:title}), pre);
    if (attrs.open) pre.textContent = JSON.stringify(value, null, 2);
    return details;
  }
  function paintControls() {
    if (!visible()) return;
    const controls = vm.view.querySelector('[data-graph-controls]'); if (!controls) return;
    const valid = vm.checked && vm.checked.revision === vm.revision;
    const busy = !!vm.busy || !!vm.compositionBusy;
    controls.replaceChildren(el('div', {class:'sy-graph-actions'},
      el('button', {class:'btn', text:vm.busy === 'check' ? 'Checking…' : 'Check graph', disabled:busy || !vm.raw,
        on:{click:check}}),
      el('button', {class:'btn primary', text:vm.busy === 'run' ? 'Starting…' : 'Run checked graph', disabled:busy || !valid,
        on:{click:run}})),
      el('p', {class:'hint', text:'Check makes no model calls. Run executes the reviewed, frozen graph under its declared routing policy and call limits.'}));
    if (vm.error) controls.appendChild(el('p', {role:'alert', class:'sy-graph-error', text:vm.error}));
    if (vm.notice) controls.appendChild(el('p', {role:'status', text:vm.notice}));
    if (valid) {
      const value = vm.checked.response;
      controls.appendChild(el('div', {'data-graph-check':'', class:'sy-graph-check'},
        el('h3', {text:'Reviewed graph contract'}),
        el('p', {text:(Array.isArray(value.nodes) ? value.nodes.length : value.nodes) + ' nodes · ' + value.iterations + ' finite iteration(s) · at most ' + value.max_calls + ' reserved calls'}),
        el('p', {text:'Ready: ' + (value.ready || []).map(item => typeof item === 'string' ? item : item.node || item.id || JSON.stringify(item)).join(', ')}),
        el('p', {class:'hint', text:typeof value.scope === 'string' ? value.scope : JSON.stringify(value.scope)}),
        el('p', {class:'hint', text:'This check validates supported structure and declared contracts. It does not establish the truth of premises, semantic fidelity, or model reliability.'}),
        jsonDetails('Reviewed hashes and check receipt', value)));
    } else if (vm.raw) controls.appendChild(el('p', {class:'hint', text:'Check this draft to review its limits and enable Run. Any edit invalidates the previous check.'}));
    const exampleButton = vm.view.querySelector('[data-graph-example]');
    if (exampleButton) exampleButton.disabled = busy;
    paintComposition();
  }
  function paintOverview() {
    if (!visible()) return;
    const overview = vm.view.querySelector('[data-graph-overview]'); if (!overview) return;
    overview.replaceChildren();
    let value; try { value = parse(); } catch (_) { return; }
    const graph = value.graph;
    overview.appendChild(el('h3', {text:graph.title || graph.id || 'Graph draft'}));
    if (vm.description) overview.appendChild(el('p', {class:'hint', text:vm.description}));
    if (!Array.isArray(graph.nodes)) return;
    const nodes = el('ol', {class:'sy-graph-nodes', 'aria-label':'Draft nodes and dependencies'});
    graph.nodes.slice(0, 128).forEach(node => {
      if (!node || typeof node !== 'object') return;
      const refs = Object.entries(node.inputs || {}).map(([key, ref]) => {
        if (!ref || typeof ref !== 'object') return key + ': invalid reference';
        return key + ' ← ' + (ref.node ? ref.node + (ref.delay ? ' (previous iteration; seeded)' : '') : 'literal input');
      });
      nodes.appendChild(el('li', {}, el('strong', {text:node.id || 'Unnamed node'}),
        el('p', {text:node.contract || 'No authored contract'}),
        el('p', {class:'hint', text:refs.length ? refs.join(' · ') : 'No incoming values'})));
    });
    overview.appendChild(nodes);
  }
  function paintRuns() {
    if (!visible()) return;
    const list = vm.view.querySelector('[data-graph-runs]'); if (!list) return;
    list.replaceChildren();
    if (vm.listError) list.appendChild(el('p', {role:'alert', class:'sy-graph-error', text:vm.listError}));
    if (!vm.runs.length) list.appendChild(el('p', {class:'hint', text:'No saved graph runs were returned.'}));
    vm.runs.forEach(row => list.appendChild(el('button', {class:'btn sy-graph-saved', 'aria-pressed':row.id === vm.selected ? 'true' : 'false',
      text:(row.title || row.id) + ' · ' + row.status + (row.reserved_calls === undefined ? '' : ' · ' + row.reserved_calls + ' reserved calls'),
      on:{click:() => {clearTimeout(vm.timer); vm.selected = row.id; vm.run = null; vm.runError = ''; vm.receipts = false; vm.nodePage = 0; save(); paintRuns(); paintRun(); readRun(row.id);}}})));
  }
  function paintRun() {
    if (!visible()) return;
    const view = vm.view.querySelector('[data-graph-run]'); if (!view) return;
    view.replaceChildren();
    if (vm.runError) view.appendChild(el('p', {role:'alert', class:'sy-graph-error', text:vm.runError}));
    if (!vm.selected) return;
    const result = vm.run;
    view.appendChild(el('h3', {text:'Selected run · ' + vm.selected}));
    if (!result) {
      view.append(el('p', {class:'hint', text:'Reading saved run…'}),
        el('button', {class:'btn', text:'Refresh selected run', on:{click:()=>readRun(vm.selected)}})); return;
    }
    const state = result.state, status = state.status || result.meta?.status || 'unrecorded';
    view.append(el('p', {'data-graph-status':'', role:'status', text:'Recorded status: ' + status + ' · ' +
      (state.reserved_calls ?? 'unrecorded') + ' reserved calls · worker ' + (result.active ? 'active' : 'inactive')}),
      el('p', {class:'hint', text:'Reservations are call limits, not measured usage. Supported node outcomes describe the declared checks and assumptions; they are not truth guarantees.'}));
    if (result.scope || result.meta?.scope) view.appendChild(el('p', {class:'hint', text:'Recorded scope: ' + (result.scope || result.meta.scope)}));
    if (result.error || state.error) view.appendChild(el('p', {class:'sy-graph-error', text:result.error || state.error}));
    const terminal = ['done', 'completed', 'succeeded', 'cancelled', 'canceled', 'exhausted', 'unresolved'].includes(status);
    const resumable = result.can_resume === true && !result.active && !terminal;
    view.append(el('div', {class:'sy-graph-actions'},
      el('button', {class:'btn', text:'Refresh selected run', disabled:!!vm.busy, on:{click:()=>readRun(vm.selected)}}),
      el('button', {class:'btn danger', text:'Stop graph', disabled:!!vm.busy || terminal, on:{click:()=>control('stop')}}),
      el('button', {class:'btn', text:'Resume graph', disabled:!!vm.busy || !resumable, on:{click:()=>control('resume')}})),
      el('p', {class:'hint', text:'Stop requests cancellation. Resume asks the server to recover this saved run; it cannot silently repeat an uncertain attempt.'}));
    const states = Array.isArray(state.nodes) ? state.nodes : Object.entries(state.nodes || {}).map(([id,node])=>
      typeof node === 'object' && node ? {id,...node} : {id,status:node});
    const rows = el('ul', {class:'sy-graph-results', 'aria-label':'Recorded node outcomes'});
    const pageCount = Math.max(1, Math.ceil(states.length / 20));
    vm.nodePage = Math.min(vm.nodePage, pageCount - 1);
    states.slice(vm.nodePage * 20, (vm.nodePage + 1) * 20).forEach(node => {
      const item = el('li', {}, el('strong', {text:(node.node || node.id || 'Node') +
        (node.iteration === undefined ? '' : ' · iteration ' + node.iteration)}),
        el('p', {text:'Status: ' + (node.status || 'unrecorded')}));
      if (node.result !== undefined) {
        if (node.result && typeof node.result === 'object') {
          item.appendChild(el('p', {text:'Recorded outcome: ' + (node.result.outcome || 'unrecorded')}));
          const value = node.result.value;
          if (value === null || ['string', 'number', 'boolean'].includes(typeof value)) {
            const rendered = JSON.stringify(value);
            item.appendChild(el('p', {text:'Value: ' + rendered.slice(0, 240) + (rendered.length > 240 ? '… (full value in receipt)' : '')}));
          }
        }
        item.appendChild(jsonDetails('Recorded result for ' + (node.node || node.id || 'node'), node.result));
      }
      if (node.error) item.appendChild(el('p', {text:node.error}));
      rows.appendChild(item);
    });
    if (states.length > 20) view.appendChild(el('div', {class:'sy-graph-actions'},
      el('p', {text:'Node outcomes ' + (vm.nodePage * 20 + 1) + '–' + Math.min(states.length, (vm.nodePage + 1) * 20) + ' of ' + states.length}),
      el('button', {class:'btn', text:'Previous node outcomes', disabled:vm.nodePage === 0, on:{click:()=>{vm.nodePage--; paintRun();}}}),
      el('button', {class:'btn', text:'Next node outcomes', disabled:vm.nodePage === pageCount - 1, on:{click:()=>{vm.nodePage++; paintRun();}}})));
    view.appendChild(rows);
    const receipt = jsonDetails('Full state and event receipts', result, {open:vm.receipts});
    receipt.addEventListener('toggle', () => {if (receipt.isConnected) vm.receipts = receipt.open;});
    view.appendChild(receipt);
  }
  function render(mount) {
    clearTimeout(vm.timer);
    vm.epoch++; vm.compositionTicket++; vm.compositionBusy = '';
    vm.mount = mount; vm.view = el('div', {class:'sy-graphs'}); mount.replaceChildren(vm.view);
    const editor = el('textarea', {id:'sy-graph-json', rows:16, maxlength:LIMIT, value:vm.raw, spellcheck:'false',
      on:{input:event => {vm.description = ''; change(event.target.value);}}});
    const advanced = el('details', {open:vm.advanced, 'data-graph-advanced':''}, el('summary', {text:'Edit graph and routing policy JSON'}),
      el('p', {class:'hint', text:'Declare nodes, input edges, finite iterations, retry and call caps, and allowed routes. Delayed edges require explicit seeds. The server refuses unsupported effects or routing; editing does not execute anything.'}),
      el('label', {for:'sy-graph-json', text:'Graph document · graph and policy'}), editor,
      el('button', {class:'btn', 'data-graph-example':'', text:'Load deterministic example', disabled:!!vm.busy, on:{click:example}}));
    advanced.addEventListener('toggle',()=>{if(advanced.isConnected) vm.advanced = advanced.open;});
    const compositionEditor = el('textarea', {id:'sy-graph-composition', rows:14, maxlength:LIMIT, value:vm.composition, spellcheck:'false',
      on:{input:event=>changeComposition(event.target.value)}});
    const composition = el('details', {open:vm.compositionOpen, 'data-graph-composition':''},
      el('summary', {text:'Advanced: compose reusable graph fragments'}),
      el('p', {class:'hint', text:'Keep reusable definitions and exact instance inputs here. Expand to flat draft replaces the future graph and policy below; then use Check graph and Run checked graph. Expansion makes no model calls and creates no run.'}),
      el('p', {class:'hint', text:'The composition and mapping are retained only in this browser session. Saved runs recover their flat graph, not this authoring source. Port labels and hashes do not prove intent or premise truth.'}),
      el('label', {for:'sy-graph-composition', text:'Composition document · composition and policy'}), compositionEditor,
      el('div', {'data-composition-controls':''}), el('div', {'data-composition-receipt':''}));
    composition.addEventListener('toggle',()=>{if(composition.isConnected) vm.compositionOpen = composition.open;});
    vm.view.append(el('section', {class:'unit', 'aria-labelledby':'sy-graphs-title'},
      el('span', {class:'lbl', text:'Contracted agent graphs'}), el('h2', {id:'sy-graphs-title', text:'Connect explicit steps. Keep their receipts.'}),
      el('p', {class:'hint', text:'Start with a deterministic two-node example. Graphs connect bounded Symblic programs through declared inputs and checking contracts. A graph is an execution structure; it does not train a neural network or establish independent evidence.'}),
      el('div', {'data-graph-overview':''}), composition, advanced, el('div', {'data-graph-controls':''})),
      el('section', {class:'unit', 'aria-labelledby':'sy-graphs-saved'}, el('h2', {id:'sy-graphs-saved', text:'Saved graph runs'}),
        el('button', {class:'btn', text:'Refresh saved runs', on:{click:refreshRuns}}),
        el('div', {'data-graph-runs':''}), el('div', {'data-graph-run':''})));
    paintOverview(); paintControls(); paintRuns(); paintRun();
    refreshRuns(); if (vm.selected) readRun(vm.selected);
    if (!vm.raw && !vm.loadingExample) example();
  }
  async function importPolicy(policy, provenance) {
    if (vm.busy) throw new Error('The graph draft is busy. Finish its current check or run request before copying a policy.');
    const revision = vm.revision;
    if (!policy || typeof policy !== 'object' || Array.isArray(policy)) throw new Error('The selected policy is invalid.');
    checkResponseNumbers(policy);
    // An explicit policy copy changes only this future draft. Invalid existing
    // graph text must be repaired by its author, never discarded by this bridge.
    let document;
    if (vm.raw.trim()) document = parse();
    else {
      const example = await Studio.api(API + 'example');
      checkResponseNumbers(example);
      if (!example.graph) throw new Error('Load or repair a graph draft before copying this policy.');
      document = {graph:example.graph};
    }
    if (revision !== vm.revision) throw new Error('The graph draft changed while the policy was loading. Review it and copy again.');
    change(JSON.stringify({graph:document.graph, policy}, null, 2));
    vm.description = ''; vm.advanced = true;
    vm.notice = 'Copied routing policy ' + (provenance?.policy_hash || '') + ' into this future graph draft. Existing runs keep their recorded policies. Check this edited draft before running.';
  }
  window.SymblicGraphs = {render, importPolicy};
})();
