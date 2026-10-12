/* Symblic Interpreter: explicit intent, clarification, read-back and a checked handoff to the host's runner.
   Inert until the existing Symblic page calls render(). All text is inserted as text nodes. */
(function () {
  'use strict';
  const API = '/api/automation/symblic/intent/';
  const ACTIVE = new Set(['queued', 'running']);
  const PENDING = new Set(['queued', 'running', 'uncertain']);
  const vm = { view: null, list: null, mount: null, busy: false, error: '', notice: '', draft: '', sourceDraft: '',
    draftBy: '', picker: null, pickerTarget: null, confidential: false, newRequireQuestion: true, questionModes: {}, requestId: '', edited: '', dirty: false, timer: null, polls: 0, listOpen: false, answers: {}, corrections: {}, predicates: {}, initialized: false, readEpoch: 0, jobRequests: {} };

  function node(tag, attrs, ...children) {
    const el = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === 'text') el.textContent = value == null ? '' : String(value);
      else if (key === 'on') Object.entries(value).forEach(([event, fn]) => el.addEventListener(event, fn));
      else if (key === 'class') el.className = value;
      else if (['value', 'disabled', 'checked', 'hidden', 'open'].includes(key)) el[key] = value;
      else if (value !== null && value !== undefined) el.setAttribute(key, String(value));
    });
    children.flat().forEach((child) => {
      if (child !== null && child !== undefined) el.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    if (attrs && Object.prototype.hasOwnProperty.call(attrs, 'value')) el.value = attrs.value;
    return el;
  }
  const text = (tag, value, cls) => node(tag, { class: cls || '', text: value });
  const arr = (value) => Array.isArray(value) ? value : [];
  const state = () => vm.view && vm.view.state;
  const working = () => PENDING.has(vm.view && vm.view.job && vm.view.job.status);
  const locked = () => vm.busy || working();
  function uuid() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return 'ui-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
  }
  function message(error) { return error && error.message ? String(error.message) : String(error || 'Request failed.'); }
  async function api(route, body) {
    const opts = { credentials: 'same-origin', cache: 'no-store' };
    if (body !== undefined) Object.assign(opts, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let response;
    try { response = await fetch(API + route, opts); }
    catch (_) { throw new Error('Connection lost. Refresh the saved intent before retrying; the request may have reached the server. Your edits are kept here.'); }
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error('The server returned an unreadable reply. Refresh the saved intent before retrying.'); }
    if (!response.ok || data.success === false) {
      const err = new Error(response.status === 409
        ? 'This intent changed elsewhere. Your edits are kept here. Refresh the saved intent before continuing.'
        : typeof data.error === 'string' ? data.error : data.error && data.error.message || 'That request could not be completed (' + response.status + ').');
      err.status = response.status;
      throw err;
    }
    return data;
  }
  function persistJobRequests() {
    try { sessionStorage.setItem('symblic-intent-jobs', JSON.stringify(vm.jobRequests)); } catch (_) { }
  }
  function restoreJobRequests() {
    try {
      const saved = JSON.parse(sessionStorage.getItem('symblic-intent-jobs') || '{}');
      if (!saved || Array.isArray(saved) || typeof saved !== 'object') return;
      Object.entries(saved).slice(-16).forEach(([key, value]) => {
        let parts;
        try { parts = JSON.parse(key); } catch (_) { return; }
        if (Array.isArray(parts) && [3, 4].includes(parts.length) && typeof parts[0] === 'string'
            && /^[a-zA-Z0-9_-]{1,100}$/.test(parts[0]) && Number.isInteger(parts[1]) && parts[1] >= 0
            && ['analyse', 'compile'].includes(parts[2]) && typeof value === 'string' && value.length > 0 && value.length <= 100
            && (parts.length === 3 || parts[2] === 'analyse' && typeof parts[3] === 'boolean')) {
          // Legacy analyses used the server's false default. Never reuse one
          // for a new request that explicitly requires a question.
          if (parts.length === 3 && parts[2] === 'analyse') parts.push(false);
          vm.jobRequests[JSON.stringify(parts)] = value;
        }
      });
    } catch (_) { }
  }
  function persistQuestionModes() {
    try { sessionStorage.setItem('symblic-intent-question-modes', JSON.stringify(vm.questionModes)); } catch (_) { }
  }
  function restoreQuestionModes() {
    try {
      const saved = JSON.parse(sessionStorage.getItem('symblic-intent-question-modes') || '{}');
      if (!saved || Array.isArray(saved) || typeof saved !== 'object') return;
      Object.entries(saved).slice(-16).forEach(([id, value]) => {
        if (/^[a-zA-Z0-9_-]{1,100}$/.test(id) && !['__proto__', 'constructor', 'prototype'].includes(id) && typeof value === 'boolean') vm.questionModes[id] = value;
      });
    } catch (_) { }
  }
  function questionMode() {
    const s = state();
    const input = node('input', { type: 'checkbox', 'aria-label': 'Ask for specifics',
      checked: s ? vm.questionModes[s.id] !== false : vm.newRequireQuestion, disabled: locked(),
      on: { change: () => {
        if (locked()) return;
        if (s) { vm.questionModes[s.id] = input.checked; persistQuestionModes(); }
        else vm.newRequireQuestion = input.checked;
      } } });
    return node('div', {}, node('label', { class: 'si-check' }, input, text('span', 'Ask for specifics')),
      text('p', 'Ask a follow-up question before translating a model interpretation. Turn off for readback only. Built-in workflows can proceed directly. A question does not prove the interpretation is correct.', 'hint'));
  }
  async function startJob(kind) {
    const s = state(), requireQuestion = vm.questionModes[s.id] !== false;
    const key = JSON.stringify(kind === 'analyse' ? [s.id, s.revision, kind, requireQuestion] : [s.id, s.revision, kind]);
    vm.jobRequests[key] = vm.jobRequests[key] || uuid();
    persistJobRequests();
    try {
      const body = { id: s.id, revision: s.revision, request_id: vm.jobRequests[key] };
      if (kind === 'analyse') body.require_question = requireQuestion;
      const response = await api(kind, body);
      accept(response, false);
      delete vm.jobRequests[key]; persistJobRequests();
    } catch (error) {
      // Only a definite client refusal releases this identity. Lost replies,
      // unreadable replies and server failures keep it for the same logical retry.
      if (error.status >= 400 && error.status < 500) { delete vm.jobRequests[key]; persistJobRequests(); }
      throw error;
    }
  }
  function editorText(s) {
    const turns = arr(s.turns).filter((turn) => turn.kind === 'rewrite');
    return String(turns.length ? turns[turns.length - 1].text : s.goal || '');
  }
  function accept(data, resetEditor) {
    if (!data || !data.state || typeof data.state.id !== 'string') throw new Error('The server reply did not contain an intent.');
    const previous = state();
    if (previous && previous.id === data.state.id && data.state.revision < previous.revision) return;
    if (!previous || previous.id !== data.state.id) { vm.answers = {}; vm.corrections = {}; }
    const answered = arr(data.state.questions).filter((q) => q.status === 'answered');
    const earlier = new Set(previous && previous.id === data.state.id ? arr(previous.questions).filter((q) => q.status === 'answered').map((q) => q.id) : []);
    if (typeof vm.questionModes[data.state.id] !== 'boolean') vm.questionModes[data.state.id] = !answered.length;
    else if (previous && previous.id === data.state.id && answered.some((q) => !earlier.has(q.id))) vm.questionModes[data.state.id] = false;
    persistQuestionModes();
    vm.view = data;
    const acknowledgedJob = data.requested_job || data.job;
    if (acknowledgedJob && typeof acknowledgedJob.request_id === 'string') {
      Object.keys(vm.jobRequests).forEach((key) => { if (vm.jobRequests[key] === acknowledgedJob.request_id) delete vm.jobRequests[key]; });
      persistJobRequests();
    }
    if (resetEditor || !vm.dirty || !previous || previous.id !== data.state.id) {
      vm.edited = editorText(data.state);
      vm.dirty = false;
    }
    vm.polls = 0;
  }
  function remember() {
    try { if (state()) sessionStorage.setItem('symblic-intent-id', state().id); else sessionStorage.removeItem('symblic-intent-id'); } catch (_) { }
  }
  function repaint() { if (vm.mount && vm.mount.isConnected !== false) draw(vm.mount); }
  async function action(fn, allowWorking) {
    if (vm.busy || (working() && !allowWorking)) return;
    vm.readEpoch++; vm.busy = true; vm.error = ''; vm.notice = ''; repaint();
    try { await fn(); }
    catch (e) { vm.error = message(e); }
    finally { vm.busy = false; repaint(); schedule(); }
  }
  async function refresh() {
    if (!state() || vm.busy) return;
    vm.readEpoch++; vm.busy = true; vm.error = ''; repaint();
    try { accept(await api('view?id=' + encodeURIComponent(state().id)), false); }
    catch (e) { vm.error = message(e); }
    finally { vm.busy = false; repaint(); schedule(); }
  }
  async function revise(kind, payload) {
    if (vm.dirty && kind !== 'rewrite') throw new Error('Save your clarified request before changing other details.');
    const s = state();
    accept(await api('revise', { id: s.id, revision: s.revision, event: { id: uuid(), kind, payload } }), true);
    vm.notice = 'Saved. Any earlier translation is now out of date.';
  }
  function schedule() {
    clearTimeout(vm.timer); vm.timer = null;
    if (!ACTIVE.has(vm.view && vm.view.job && vm.view.job.status) || vm.error || vm.busy || !vm.mount || vm.mount.isConnected === false) return;
    if (vm.polls >= 150) { vm.notice = 'Automatic status checks paused. Refresh the saved intent to continue.'; repaint(); return; }
    vm.timer = setTimeout(async () => {
      if (!vm.mount || vm.mount.isConnected === false) return;
      const count = vm.polls + 1, epoch = vm.readEpoch, id = state().id;
      try {
        const data = await api('view?id=' + encodeURIComponent(id));
        if (epoch !== vm.readEpoch || !state() || state().id !== id) return;
        accept(data, false); vm.polls = count;
      }
      catch (e) { vm.error = message(e); }
      repaint(); schedule();
    }, 2000);
  }
  function button(label, fn, disabled, primary) {
    return node('button', { type: 'button', class: 'btn' + (primary ? ' primary' : ''), text: label,
      disabled: !!disabled, on: { click: fn } });
  }
  function field(label, value, onInput, opts) {
    const o = opts || {};
    const input = node('textarea', { class: 'field si-input' + (o.code ? ' si-code' : ''), 'aria-label': label,
      value: String(value || ''), rows: o.rows || 4, maxlength: o.max || 40000, disabled: !!o.disabled,
      readonly: o.readonly ? '' : null, on: { input: () => onInput && onInput(input.value) } });
    return { input, wrap: node('label', { class: 'si-field' }, text('span', label, 'lbl'), input) };
  }
  function quotes(refs) {
    if (!arr(refs).length) return null;
    return node('details', { class: 'si-quotes' }, text('summary', 'Source wording'), arr(refs).map((ref) =>
      node('blockquote', {}, text('p', ref.quote || ''), text('footer', String(ref.source_id || '') + ' · source characters ' + ref.start + '–' + ref.end, 'hint'))));
  }
  function listItems(title, rows, render) {
    if (!rows.length) return null;
    return node('section', { class: 'si-section' }, text('h3', title), rows.map(render));
  }
  function summaryCard(item, detail) {
    return node('div', { class: 'si-item' }, text('p', item.text || item.description || ''),
      detail ? text('p', detail, 'hint') : null, quotes(item.source_refs));
  }
  function budget() {
    const b = vm.view && vm.view.budget;
    if (!b) return null;
    return text('p', 'Interpretation calls: ' + (b.used == null ? '?' : b.used) + ' used of ' + (b.limit == null ? '?' : b.limit)
      + (b.repairs_limit == null ? '' : '; repairs ' + (b.repairs_used || 0) + ' of ' + b.repairs_limit)
      + '. The later host run has its own budget.', 'hint');
  }
  function question(q) {
    const draft = vm.answers[q.id] || (vm.answers[q.id] = { text: '', option: '' });
    const choice = node('select', { class: 'field', 'aria-label': 'Choice for ' + q.question, disabled: locked(), value: draft.option,
      on: { change: () => { draft.option = choice.value; } } }, node('option', { value: '', text: 'Choose or write an answer' }),
    arr(q.options).map((o) => node('option', { value: o.id, text: o.label })));
    const answerField = field('Answer: ' + q.question, draft.text, (v) => { draft.text = v; }, { rows: 2, disabled: locked() });
    return node('section', { class: 'si-item' }, text('h3', q.question), text('p', q.why || '', 'hint'),
      q.blocking ? text('p', 'Needed before translation', 'si-needed') : null,
      arr(q.options).length ? choice : null,
      arr(q.options).map((o) => o.consequence ? text('p', o.label + ': ' + o.consequence, 'hint') : null),
      answerField.wrap, quotes(q.source_refs), button('Save answer', () => {
        if (!draft.text.trim() && !draft.option) { vm.error = 'Choose an option or write an answer.'; repaint(); return; }
        action(() => revise('answer', { question_id: q.id, option_id: draft.option || undefined, text: draft.text }));
      }, locked()));
  }
  function requirement(r) {
    const card = summaryCard(r, (r.kind || 'requirement') + ' · ' + (r.origin || ''));
    const key = state().id + ':' + r.id;
    const predicate = field('Check expression for ' + r.id, vm.predicates[key] === undefined ? r.predicate || '' : vm.predicates[key],
      (v) => { vm.predicates[key] = v; }, { rows: 2, max: 12000, disabled: locked() });
    card.appendChild(node('details', {}, text('summary', 'Declare an executable check expression'),
      text('p', 'Optional: name program bindings in a Symblic expression, such as total = 120. Translation will report whether this exact predicate appears. Declaring it does not execute it or prove that it captures the prose.', 'hint'),
      predicate.wrap, button('Save check expression ' + r.id, () => action(async () => {
        const value = vm.predicates[key] === undefined ? r.predicate || '' : vm.predicates[key];
        if (!value.trim()) throw new Error('Enter a check expression first.');
        await revise('predicate', { requirement_id: r.id, predicate: value });
        delete vm.predicates[key];
      }), locked())));
    const reason = field('Correction reason for ' + r.id, vm.corrections[r.id] || '', (v) => { vm.corrections[r.id] = v; }, { rows: 2, max: 4000, disabled: locked() });
    card.appendChild(node('details', {}, text('summary', 'Correct this requirement'), reason.wrap,
      button('Retire requirement ' + r.id, () => action(async () => {
        if (!(vm.corrections[r.id] || '').trim()) throw new Error('Explain why this requirement is incorrect or no longer applies.');
        await revise('requirement', { requirement_id: r.id, status: 'retired', reason: vm.corrections[r.id] });
      }), locked())));
    return card;
  }
  function assumption(a) {
    return node('div', { class: 'si-item' }, text('p', a.text), text('p', (a.status || 'proposed') + (a.consequence ? ' · ' + a.consequence : ''), 'hint'),
      quotes(a.source_refs), a.status === 'proposed' ? node('div', { class: 'si-actions' },
        button('Use this assumption', () => action(() => revise('assumption', { assumption_id: a.id, status: 'adopted' })), locked()),
        button('Reject assumption', () => action(() => revise('assumption', { assumption_id: a.id, status: 'rejected' })), locked())) : null);
  }
  function safeRunnerUrl(value) { return typeof value === 'string' && /^\/runner(?:\/|[?#]|$)/.test(value) && !/[\\\s]/.test(value) ? value : ''; }
  function readyToTranslate() {
    const s = state(), readiness = vm.view && vm.view.validation && vm.view.validation.readiness;
    const phase = readiness && readiness.phase || s && s.phase;
    return !currentHandoff() && !(readiness && readiness.analysis_required) && ['specified', 'checked'].includes(phase)
      && !arr(s && s.questions).some((q) => q.status === 'pending' && q.blocking);
  }
  function currentHandoff() {
    const s = state(), h = vm.view && vm.view.handoff;
    return !!(s && (s.handoff || s.phase === 'handed_off')) || !!(h &&
      (h.content_revision == null || h.content_revision === (s && s.content_revision)));
  }
  const short = (value, limit) => {
    const raw = typeof value === 'string' ? value : '';
    return raw.length > limit ? raw.slice(0, limit) + '…' : raw;
  };
  function compatibility() {
    const c = vm.view && vm.view.artifact_compatibility;
    if (c == null) return null; // Older APIs do not report this metadata.
    const valid = typeof c === 'object' && !Array.isArray(c) && ['current', 'stale', 'unknown'].includes(c.status)
      && Array.isArray(c.differences) && c.differences.length <= 6
      && c.differences.every((v) => ['intent', 'kernel', 'modules', 'catalogue', 'policy', 'sources'].includes(v))
      && (c.status !== 'current' || c.differences.length === 0);
    return valid ? c : { status: 'unknown', message: 'The compatibility reply was not recognized.' };
  }
  function canStartTranslation() {
    const c = compatibility();
    return !c || c.status === 'current';
  }
  function compatibilityNotice() {
    const c = compatibility();
    if (currentHandoff()) return text('p', 'This request already has a host handoff. Open its run or check its status. Revise the request or create a new interpretation before translating another program.', 'hint');
    if (!c) return text('p', 'Current runtime compatibility is not reported by this API. The server checks it before a new run.', 'hint');
    const headings = { current: 'Translation matches the current runtime and saved contract.',
      stale: 'Translate and check again before starting a new run. The runtime or saved contract changed.',
      unknown: 'Current compatibility could not be checked. Refresh the saved intent, then translate again when metadata is available.' };
    const differences = arr(c.differences).filter((v) => ['intent', 'kernel', 'modules', 'catalogue', 'policy', 'sources'].includes(v));
    return node('div', { class: 'si-compat', role: 'status' }, text('p', headings[c.status], c.status === 'current' ? 'hint' : 'si-needed'),
      c.message ? text('p', short(c.message, 600), 'hint') : null,
      differences.length ? text('p', 'Changed: ' + [...new Set(differences)].join(', ') + '.', 'hint') : null);
  }
  function interpretationEvidence() {
    const s = state(), job = vm.view.job || {}, e = job.evidence || {}, a = vm.view.artifact || {};
    const mechanism = e.mechanism || (e.observation ? 'model_proposal' : '');
    const names = { deterministic_recipe_match: 'Built-in workflow match', model_proposal: 'Model proposal' };
    const questionChecks = { presence_only: 'A pending clarification question was required; this checks presence, not its usefulness.',
      not_requested: 'A clarification question was not required for this analysis.',
      not_needed_deterministic_recipe: 'The built-in workflow needed no model question.' };
    const adopted = arr(s.assumptions).filter((r) => r.status === 'adopted');
    const answered = arr(s.questions).filter((q) => q.status === 'answered');
    const refs = [];
    const seen = new Set();
    [...arr(s.requirements), ...arr(s.assumptions), ...arr(s.questions), ...arr(s.examples)].forEach((row) => {
      arr(row.source_refs).forEach((ref) => {
        if (!ref || typeof ref.quote !== 'string' || !ref.quote) return;
        const key = JSON.stringify([ref.source_id, ref.start, ref.end, ref.quote]);
        if (!seen.has(key)) { seen.add(key); refs.push(ref); }
      });
    });
    const checks = arr(a.checks);
    const staticNames = { static: 'Language and input checks', effect_static: 'Declared capability checks' };
    return node('details', { class: 'si-section si-evidence' }, text('summary', 'Interpretation evidence'),
      text('p', 'These records describe this interpretation. They do not prove intended meaning or external truth.', 'hint'),
      text('h3', 'Analysis'),
      text('p', names[mechanism] || 'Analysis mechanism unavailable in this reply.', 'hint'),
      text('p', questionChecks[e.question_check] || 'Question-check evidence unavailable in this reply.', 'hint'),
      text('p', e.feedback_exposed === true ? 'An earlier rejected answer’s feedback was exposed to a later candidate.'
        : e.feedback_exposed === false ? 'This analysis reports no earlier-candidate feedback exposure.'
          : 'Feedback exposure was not reported in this reply.', 'hint'),
      text('p', 'Observational independence is not established by these records.', 'hint'),
      text('h3', 'Owner decisions'),
      text('p', answered.length + ' answered clarification' + (answered.length === 1 ? '' : 's') + '; '
        + adopted.length + ' adopted assumption' + (adopted.length === 1 ? '' : 's') + '. Decisions guide the task; adopted assumptions are not observed facts.', 'hint'),
      adopted.slice(0, 6).map((r) => text('p', short(r.text, 500), 'si-evidence-quote')),
      adopted.length > 6 ? text('p', 'First 6 adopted assumptions shown here; the complete list is below.', 'hint') : null,
      text('h3', 'Source correspondence'),
      text('p', refs.length ? 'Retained exact quotes identify source wording. Their presence does not establish entailment or factual accuracy.'
        : 'No exact source quotes are attached to the displayed interpretation.', 'hint'),
      refs.slice(0, 6).map((ref) => node('blockquote', { class: 'si-evidence-quote' },
        text('p', short(ref.quote, 500)), text('footer', short(ref.source_id, 100) + ' · source characters ' + ref.start + '–' + ref.end, 'hint'))),
      refs.length > 6 ? text('p', 'First 6 distinct quotes shown here; complete references remain with their items.', 'hint') : null,
      text('h3', 'Translation checks and examples'),
      text('p', 'Requirements are retained; the static map and observed execution checks are shown separately.', 'hint'),
      checks.length ? checks.slice(0, 8).map((c) => text('p',
        (staticNames[c.kind] || 'Other receipt: ' + short(c.kind, 80)) + ' · '
          + (c.ok === true ? 'passed' : c.ok === false ? 'failed' : 'result unavailable') + ' · ' + short(c.scope, 600), 'hint'))
        : text('p', 'No translation-check receipts are available yet.', 'hint'),
      checks.length > 8 ? text('p', 'First 8 receipts shown; all supplied receipts are in Exact inputs and check receipt.', 'hint') : null,
      text('p', arr(s.examples).length + ' proposed example' + (arr(s.examples).length === 1 ? '' : 's')
        + ' in the read-back. Proposed examples have not been executed by this view. Static checks do not execute the program.', 'hint'),
      text('p', 'Executed predicate or mathematical checks belong to the host run. Open its run link to inspect those results.', 'hint'));
  }
  function artifact() {
    const a = vm.view.artifact;
    const s = state();
    const h = vm.view.handoff || s.handoff;
    const url = safeRunnerUrl(h && h.url);
    if (!a || typeof a.source !== 'string') return h ? node('section', { class: 'si-section' },
      text('h2', 'Earlier host handoff'),
      text('p', 'Recorded status: ' + (h.status || 'recorded') + '. This run belongs to its saved translation.', 'hint'),
      url ? node('a', { class: 'btn', href: url, text: 'Open host run' }) : null) : null;
    const check = a.check || {};
    const blocking = arr(s.questions).some((q) => q.status === 'pending' && q.blocking);
    const checked = check.ok === true && !vm.dirty && !blocking && s.phase === 'checked' && readyToTranslate() && canStartTranslation();
    return node('section', { class: 'si-section' }, text('h2', 'Translation and checks'),
      text('p', check.ok === true ? 'The encoded program passed its reported checks. This does not prove it captures everything you meant.'
        : 'The translation needs attention before it can run.', 'hint'),
      compatibilityNotice(),
      requirementCoverage(a, s),
      executionCoverage(),
      text('pre', a.source, 'si-source'),
      arr(check.errors).map((e) => text('p', typeof e === 'string' ? e : e.message || JSON.stringify(e), 'si-error')),
      arr(check.warnings).map((e) => text('p', typeof e === 'string' ? e : e.message || JSON.stringify(e), 'hint')),
      node('details', { class: 'si-receipt' }, text('summary', 'Exact inputs and check receipt'),
        text('pre', JSON.stringify({ inputs: a.inputs, checks: a.checks || check, coverage: a.coverage || { status: 'not_recorded' }, execution_coverage: vm.view.execution_coverage || { status: 'not_recorded' }, source_sha256: a.source_sha256, pins: a.pins || { kernel_id: a.kernel_id, module_hashes: a.module_hashes, catalogue_sha256: a.catalogue_sha256, policy_sha256: a.policy_sha256, source_hashes: a.source_hashes }, limitations: a.limitations }, null, 2), 'si-source')),
      h && ['intent', 'pending', 'uncertain'].includes(h.status) ? button('Check host handoff', () => action(async () => {
        accept(await api('reconcile', { id: s.id, revision: s.revision }), false);
      }, true), vm.busy) : null,
      h ? text('p', 'Host handoff: ' + (h.status || 'recorded') + (h.error ? ' · ' + message(h.error) : ''), 'hint') : null,
      url ? node('a', { class: 'btn', href: url, text: 'Open host run' }) : null,
      !url || !currentHandoff() ? button(currentHandoff() && h && ['intent', 'pending', 'uncertain', 'running'].includes(h.status) ? 'Handoff pending — refresh status' : 'Run on the host',
          () => action(async () => {
            if (vm.dirty || state().phase !== 'checked' || !readyToTranslate()) throw new Error('Save and check your latest wording and finish any requested clarification before running.');
            if (!canStartTranslation()) throw new Error('Refresh and translate this request again before starting a new run.');
            accept(await api('handoff', { id: s.id, revision: s.revision }), false);
          }),
          locked() || !checked || currentHandoff(), true) : null,
      text('p', 'Runs use the host runner\'s full or guarded mode. Creating a checked translation does not start a run.', 'hint'));
  }
  function requirementCoverage(a, s) {
    const c = a.coverage;
    if (!c || ![1, 2].includes(c.version) || c.scope !== 'declared_predicate_presence_only' || !Array.isArray(c.requirements))
      return text('p', 'Requirement coverage is not recorded for this translation. A static pass does not establish that every requirement is implemented.', 'si-needed');
    const missing = arr(c.unmapped_hard_ids);
    const names = new Map(arr(s.requirements).map((r) => [r.id, r.text]));
    return node('section', { class: 'si-coverage' }, text('h3', 'Requirement-to-program map'),
      text('p', 'This map locates declared predicate syntax. It does not show that a branch ran, a check passed, or the predicate captures the prose requirement.', 'hint'),
      c.version === 1 ? text('p', 'Historical map: predicate authorship was not recorded separately. Recompile for the current requirement map.', 'si-needed') : null,
      text('p', missing.length ? 'Hard requirements without a declared-predicate match: ' + missing.join(', ') + '.'
        : 'No unmapped hard requirement IDs are reported. Execution and intent fidelity remain unassessed.', missing.length ? 'si-needed' : 'hint'),
      arr(c.requirements).map((r) => node('div', {}, text('p', r.id + ' · ' + (names.get(r.id) || 'Requirement text unavailable')),
        text('p', r.status === 'predicate_present' ? (r.predicate_origin === 'owner_declared' ? 'Owner-declared predicate present; execution not assessed by this map.' : 'Predicate present; execution not assessed by this map.') : r.status === 'proposed_predicate_present' ? 'Model-proposed predicate present; requirement remains unmapped.' : r.status === 'retired' ? 'Owner-retired requirement.' : 'Unmapped; not established.', 'hint'),
        text('p', r.reason || '', 'hint'),
        arr(r.locations).length ? text('p', arr(r.locations).slice(0, 8).map((p) => p.kind + ' at line ' + p.line + ', column ' + p.col).join('; ')
          + (r.locations.length > 8 ? '. First 8 locations shown; the full manifest is in the exact receipt.' : '.'), 'hint') : null)),
      text('p', arr(c.examples).length + ' example proposals were exposed as specification context, including '
        + arr(c.examples).filter((e) => e.kind === 'negative').length + ' negative cases. None is reported as an executed or held-out test.', 'hint'));
  }
  function executionCoverage() {
    const c = vm.view.execution_coverage;
    if (!c) return null;
    const valid = c.version === 1 && c.scope === 'linked_run_retained_encoded_checks'
      && ['unknown', 'stale', 'partial', 'joined'].includes(c.status) && Array.isArray(c.requirements)
      && c.requirements.length <= 256 && c.requirements.every((r) => r && typeof r === 'object'
        && !Array.isArray(r) && typeof r.id === 'string' && typeof r.status === 'string'
        && ['observed_pass', 'observed_fail', 'partially_observed', 'ambiguous', 'unobserved', 'retired'].includes(r.status));
    if (!valid) return text('p', 'Executed requirement checks are unavailable in this reply.', 'si-needed');
    const joined = c.status === 'joined';
    const labels = { observed_pass: 'Observed passing encoded checks', observed_fail: 'Observed failing encoded checks',
      partially_observed: 'Some mapped locations observed; others unobserved', ambiguous: 'Location attribution ambiguous',
      unobserved: 'No retained check observation', retired: 'Retired requirement' };
    const count = (n) => Number.isSafeInteger(n) && n >= 0 && n <= 20000 ? n : '?';
    const observed = joined ? c.requirements.filter((r) => ['observed_pass', 'observed_fail', 'partially_observed'].includes(r.status)) : [];
    const other = joined ? c.requirements.filter((r) => !['observed_pass', 'observed_fail', 'partially_observed'].includes(r.status)) : c.requirements;
    const row = (r) => node('div', {}, text('p', short(r.id, 100) + ' · ' + (joined ? labels[r.status] || 'Unknown observation' : 'Unassessed for this saved run')),
      joined && ['observed_pass', 'observed_fail', 'partially_observed'].includes(r.status)
        ? text('p', count(r.passed_checks) + ' passing; ' + count(r.failed_checks) + ' failing retained checks.', r.failed_checks > 0 ? 'si-needed' : 'hint') : null,
      r.mapping_status === 'proposed_predicate_present' ? text('p', 'This is a model-proposed predicate; the requirement remains unmapped.', 'hint') : null);
    return node('section', { class: 'si-coverage' }, text('h3', 'Observed execution checks'),
      text('p', joined ? 'Saved source, inputs and execution pins match the linked run. These are its retained encoded check observations.'
        : c.status === 'partial' ? 'The linked run has no final retained evidence yet. Provisional trace checks are not counted.'
          : c.status === 'stale' ? 'The saved intent revision changed. Earlier run checks do not apply to this revision.'
            : 'The linked execution evidence is unavailable or cannot be matched exactly.', 'hint'),
      joined && c.binding ? text('p', 'Linked run: ' + short(c.binding.run_id, 100) + ' · status ' + short(c.run_status, 40), 'hint') : null,
      observed.length ? text('h4', 'Observed') : null, observed.map(row),
      other.length ? text('h4', 'Unobserved or unassessed') : null, other.map(row),
      text('p', 'Passing an encoded predicate does not establish intended meaning, owner acceptance, or external truth. Trace-only checks from rolled-back work do not count.', 'hint'));
  }
  function sessionPicker() {
    return node('details', { class: 'si-section', open: vm.listOpen }, text('summary', 'Saved interpretations'),
      button('Refresh saved list', () => action(async () => { vm.list = arr((await api('list')).intents); vm.listOpen = true; }), locked()),
      vm.list ? node('div', { class: 'si-sessions' }, vm.list.length ? vm.list.map((item) =>
        button((item.title || item.goal || (typeof item.request === 'string' ? item.request : item.request && item.request.text) || item.id).slice(0, 160)
          + ' · ' + (item.phase || item.status || 'saved'), () => action(async () => {
            if (vm.dirty) { vm.error = 'Save your rewritten prompt before opening another interpretation.'; return; }
            accept(await api('view?id=' + encodeURIComponent(item.id)), true); remember();
          }), locked())) : text('p', 'No saved interpretations yet.', 'hint')) : null);
  }
  function applicatorChoice() {
    const target = node('div', {});
    vm.pickerTarget = target;
    const chosen = state() && state().policy ? state().policy.by || '' : vm.draftBy;
    if (!window.SymblicPicker || !window.SymblicPicker.mountChoices)
      target.appendChild(text('p', 'Model picker unavailable. Saved choice: ' + (chosen || 'Use routing policy') + '. Refresh after the host update.', 'hint'));
    return node('section', { class: 'si-section si-applicator' }, target,
      text('p', 'This choice is saved for analysis, clarification, translation and the host run default. Changing it invalidates an earlier translation and keeps spent calls. An unavailable choice fails visibly; it never switches to another model.', 'hint'),
      text('p', (state() && state().policy && state().policy.confidential || !state() && vm.confidential)
        ? 'This request is local only. Cloud choices are refused.' : 'Cloud models still require permission in the host runner\'s policy.', 'hint'));
  }
  function draw(mount) {
    if (vm.picker) { vm.picker.destroy(); vm.picker = null; }
    vm.pickerTarget = null;
    while (mount.firstChild) mount.removeChild(mount.firstChild);
    const s = state();
    const root = node('div', { class: 'si-root' }, text('h1', 'Interpreter'),
      text('p', 'Describe what you want. Resolve the details that change the result, read back the interpretation, then translate it into checked Symblic.', 'si-lead'),
      vm.error ? text('p', vm.error, 'si-error') : null,
      vm.notice ? node('p', { class: 'si-notice', role: 'status', text: vm.notice }) : null);
    if (vm.error) root.appendChild(button('Refresh saved intent', refresh, !s || vm.busy));
    root.appendChild(sessionPicker());
    if (!s) {
      const request = field('What do you want to achieve?', vm.draft, (v) => { vm.draft = v; vm.requestId = ''; }, { rows: 7, disabled: vm.busy });
      const reference = field('Reference text (optional)', vm.sourceDraft, (v) => { vm.sourceDraft = v; vm.requestId = ''; }, { rows: 4, max: 400000, disabled: vm.busy });
      const confidential = node('input', { type: 'checkbox', checked: vm.confidential, disabled: vm.busy,
        on: { change: () => { vm.confidential = confidential.checked; vm.requestId = ''; repaint(); } } });
      root.appendChild(node('section', { class: 'si-section' }, request.wrap,
        node('details', {}, text('summary', 'Attach source text'), reference.wrap,
          text('p', 'Retained verbatim with its source hash. Sources and examples must fit compilation context; they are not silently shortened.', 'hint')),
        node('label', { class: 'si-check' }, confidential, text('span', 'Keep this request off cloud models')),
        applicatorChoice(), questionMode(),
        button('Analyse request', () => action(async () => {
          if (!vm.draft.trim()) throw new Error('Describe the result you want first.');
          vm.requestId = vm.requestId || uuid();
          const body = { request: vm.draft, confidential: vm.confidential, by: vm.draftBy, request_id: vm.requestId };
          if (vm.sourceDraft.trim()) body.sources = [{ id: 'reference-1', text: vm.sourceDraft, kind: 'document', sensitivity: vm.confidential ? 'confidential' : 'personal' }];
          const created = await api('create', body);
          if (body.by && (!created.state || !created.state.policy || created.state.policy.by !== body.by)) {
            vm.requestId = '';
            throw new Error('The host API did not save your model choice. No analysis was started. Refresh after the host update, then try again.');
          }
          if (created && created.state && typeof created.state.id === 'string') vm.questionModes[created.state.id] = vm.newRequireQuestion;
          accept(created, true); remember();
          await startJob('analyse');
        }), vm.busy, true)));
    } else {
      const pending = arr(s.questions).filter((q) => q.status === 'pending');
      root.appendChild(node('div', { class: 'si-actions' }, text('span', 'Revision ' + s.revision + ' · ' + s.phase, 'hint'),
        button('Refresh saved intent', refresh, vm.busy), button('New interpretation', () => {
          if (vm.dirty) { vm.error = 'Save your rewritten prompt before starting another interpretation.'; repaint(); return; }
          vm.readEpoch++; clearTimeout(vm.timer); vm.view = null; vm.draft = ''; vm.sourceDraft = ''; vm.draftBy = ''; vm.newRequireQuestion = true; vm.requestId = ''; vm.error = ''; vm.notice = ''; remember(); repaint();
        }, locked())));
      root.appendChild(node('details', { class: 'si-section' }, text('summary', 'Original request and later wording'),
        text('p', s.request && s.request.text || '', 'si-verbatim'), arr(s.turns).map((t) => text('p', t.text || '', 'si-verbatim'))));
      if (arr(s.sources).some((source) => source.id !== 'request' && !String(source.kind || '').startsWith('owner_')))
        root.appendChild(node('details', { class: 'si-section' }, text('summary', 'Retained source documents'),
          arr(s.sources).filter((source) => source.id !== 'request' && !String(source.kind || '').startsWith('owner_')).map((source) =>
            node('details', {}, text('summary', source.id + ' · ' + (source.kind || 'document')),
              text('p', 'SHA-256: ' + (source.sha256 || 'unavailable'), 'hint'), text('pre', source.text || '', 'si-source')))));
      root.appendChild(applicatorChoice());
      root.appendChild(budget() || text('span', ''));
      if (vm.view.job) root.appendChild(node('p', { class: 'si-job', role: 'status', text: (vm.view.job.status || '') + (vm.view.job.message ? ' · ' + vm.view.job.message : '') }));
      if (vm.view.validation && vm.view.validation.readiness && vm.view.validation.readiness.analysis_required)
        root.appendChild(text('p', 'Requested clarification did not finish. Retry analysis, or turn off Ask for specifics and analyse for a read-back.', 'si-needed'));
      if (working()) root.appendChild(button('Stop interpretation job', () => action(async () => {
        accept(await api('stop', { id: s.id, revision: s.revision }), false);
      }, true), vm.busy));
      if (pending.length) root.appendChild(node('section', { class: 'si-section' }, text('h2', 'Details that change the result'), pending.slice(0, 3).map(question)));
      if (pending.length > 3) root.appendChild(text('p', 'More than three questions were returned. Refresh or revise this interpretation before translating.', 'si-error'));
      if (s.revised_prompt || s.goal) {
        const rewritten = field('Clarified request', vm.edited, (v) => { vm.edited = v; vm.dirty = v !== editorText(s);
          save.disabled = locked() || !vm.dirty; translate.disabled = locked() || vm.dirty || !readyToTranslate(); }, { rows: 7, disabled: locked() });
        const save = button('Save clarified request', () => action(() => revise('rewrite', { text: vm.edited })), locked() || !vm.dirty);
        const translate = button('Translate and check', () => action(async () => {
          if (vm.dirty) throw new Error('Save your clarified request before translating.');
          if (!readyToTranslate()) throw new Error('Analyse this request and resolve its blocking details before translating.');
          await startJob('compile');
        }),
          locked() || vm.dirty || !readyToTranslate(), true);
        root.appendChild(node('section', { class: 'si-section' }, text('h2', 'Read back the interpretation'), rewritten.wrap,
          node('div', { class: 'si-actions' }, save, button('Copy rewritten prompt', async () => {
            if (vm.dirty) { vm.error = 'Save your clarified request before copying the full rewritten prompt.'; repaint(); return; }
            try { await navigator.clipboard.writeText(String(vm.view.readback && vm.view.readback.prompt || vm.edited)); vm.notice = 'Full rewritten prompt copied.'; }
            catch (_) { vm.notice = 'Clipboard access is unavailable. Select and copy the full prompt below.'; }
            repaint();
          }, false), translate),
          text('p', 'Your clarified request adds to the original; it does not erase earlier answers. Editing it invalidates its previous translation.', 'hint'),
          node('details', { class: 'si-section' }, text('summary', 'Full rewritten prompt and original context'),
            text('pre', vm.view.readback && vm.view.readback.prompt || vm.edited, 'si-source'))));
      }
      root.appendChild(interpretationEvidence());
      root.appendChild(node('div', { class: 'si-columns' },
        listItems('Requirements', arr(s.requirements).filter((r) => r.status !== 'retired'), requirement),
        listItems('Assumptions', arr(s.assumptions), assumption),
        listItems('Examples and counterexamples', arr(s.examples), (e) => summaryCard(e, e.kind || 'example'))));
      const errors = vm.view.validation && vm.view.validation.errors;
      if (arr(errors).length) root.appendChild(listItems('Needs attention', errors, (e) => text('p', message(e), 'si-error')));
      const unknowns = vm.view.readback && vm.view.readback.unknowns;
      if (arr(unknowns).length) root.appendChild(listItems('Still unknown', unknowns, (u) => text('p', typeof u === 'string' ? u : u.text || u.question || JSON.stringify(u), 'hint')));
      root.appendChild(questionMode());
      root.appendChild(node('div', { class: 'si-actions' }, button(s.goal ? 'Analyse again' : 'Analyse request', () => action(async () => {
        if (vm.dirty) throw new Error('Save your clarified request before analysing again.');
        await startJob('analyse');
      }), locked() || vm.dirty)));
      const out = artifact(); if (out) root.appendChild(out);
    }
    mount.appendChild(root);
    if (vm.pickerTarget && window.SymblicPicker && window.SymblicPicker.mountChoices) {
      vm.picker = window.SymblicPicker.mountChoices(vm.pickerTarget, {
        label: 'Interpreter model', searchLabel: 'Find an Interpreter model', emptyLabel: 'Use routing policy',
        getValue: () => state() && state().policy ? state().policy.by || '' : vm.draftBy,
        disabled: () => locked() || vm.dirty,
        onSelect: (spec) => {
          if (locked() || vm.dirty) return;
          if (!state()) { vm.draftBy = spec; vm.requestId = ''; repaint(); }
          else if (spec !== (state().policy && state().policy.by || ''))
            action(() => revise('applicator', { by: spec }));
        }
      });
    }
  }
  function render(mount) {
    vm.mount = mount;
    if (!vm.initialized) {
      vm.initialized = true;
      restoreJobRequests();
      restoreQuestionModes();
      let saved = '';
      try { saved = sessionStorage.getItem('symblic-intent-id') || ''; } catch (_) { }
      if (saved && !state()) action(async () => { accept(await api('view?id=' + encodeURIComponent(saved)), true); });
    }
    draw(mount); schedule();
  }
  window.SymblicIntent = { render };
})();
