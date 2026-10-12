/* Offline Interpreter journeys: fake DOM, API, timers and clipboard. No live server or stores. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '../web/studio/symblic-intent.js'), 'utf8');
class El {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.attrs = {}; this.listeners = {}; this._text = ''; this.value = ''; this.disabled = false; this.checked = false; this.isConnected = true; }
  appendChild(n) { this.children.push(n); return n; }
  removeChild(n) { this.children.splice(this.children.indexOf(n), 1); }
  get firstChild() { return this.children[0]; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map((n) => n.textContent).join(' '); }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(k, f) { (this.listeners[k] ||= []).push(f); }
  async emit(k) { for (const f of this.listeners[k] || []) await f({ target: this }); }
  async click() { if (!this.disabled) await this.emit('click'); }
  focus() { this.focused = true; }
  select() { this.selected = true; }
}
function all(el, pred) { return [el, ...el.children.flatMap((c) => all(c, pred))].filter(pred); }
function btn(w, label) { const found = all(w.mount, (n) => n.tagName === 'BUTTON' && n.textContent === label); assert(found.length, 'button missing: ' + label); return found[0]; }
function field(w, label) { const out = all(w.mount, (n) => n.attrs['aria-label'] === label)[0]; assert(out, 'field missing: ' + label); return out; }
async function fill(w, label, value) { const f = field(w, label); f.value = value; await f.emit('input'); }
function base(extra) { return Object.assign({ id: 'intent_1', revision: 1, content_revision: 1, phase: 'specified', request: { text: 'Make a flower.' }, goal: 'Describe a flower', revised_prompt: 'A red flower with five petals.', turns: [], requirements: [], assumptions: [], questions: [], examples: [] }, extra || {}); }
function envelope(s, extra) { return Object.assign({ state: s, validation: { ok: true, errors: [] }, readback: { prompt: 'Original: Make a flower. Clarification: A red flower with five petals.' }, job: null, budget: { used: 1, limit: 6, remaining: 5 }, artifact: null, handoff: null }, extra || {}); }
function world(saved) {
  const storage = typeof saved === 'object' ? { ...saved } : { 'symblic-intent-id': saved || '' };
  const w = { mount: new El('main'), calls: [], routes: {}, timers: [], copied: '', storage, now: 0 };
  const document = { createElement: (t) => new El(t), createTextNode: (t) => { const n = new El('#text'); n.textContent = t; return n; } };
  const context = { document, console, Date, Math, Set, Error, JSON, encodeURIComponent,
    navigator: { clipboard: { writeText: async (s) => { w.copied = s; } } },
    sessionStorage: { getItem: (k) => w.storage[k] || null, setItem: (k, v) => { w.storage[k] = v; }, removeItem: (k) => { delete w.storage[k]; } },
    setTimeout: (f) => { const id = ++w.now; w.timers.push({ id, f }); return id; },
    clearTimeout: (id) => { w.timers = w.timers.filter((r) => r.id !== id); },
    fetch: async (url, opts) => {
      const route = url.replace('/api/automation/symblic/intent/', '');
      const method = opts.method || 'GET'; const body = opts.body ? JSON.parse(opts.body) : undefined;
      w.calls.push({ method, route, body, opts });
      const handler = w.routes[method + ' ' + route.split('?')[0]];
      if (handler === undefined) return { ok: false, status: 404, json: async () => ({ error: 'Not ready' }) };
      const result = typeof handler === 'function' ? await handler(body, route) : handler;
      return { ok: !(result && result.__status), status: result && result.__status || 200, json: async () => JSON.parse(JSON.stringify(result)) };
    } };
  context.window = context; context.crypto = { randomUUID: () => 'uuid-' + (++w.now) };
  vm.runInNewContext(SOURCE, context);
  w.render = () => context.SymblicIntent.render(w.mount);
  w.settle = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
  w.load = async (data) => { w.routes['POST create'] = data; w.routes['POST analyse'] = data; w.render(); await fill(w, 'What do you want to achieve?', 'Make a flower.'); await btn(w, 'Analyse request').click(); await w.settle(); };
  w.tick = async () => { const t = w.timers.shift(); if (t) await t.f(); await w.settle(); };
  return w;
}
const cases = [];
function test(name, fn) { cases.push([name, fn]); }
test('inert until rendered and opening a fresh tab performs no model/API call', async () => {
  const w = world(); assert.equal(w.calls.length, 0); w.render(); assert.equal(w.calls.length, 0);
  assert(w.mount.textContent.includes('Interpreter'));
});
test('create carries stable retry identity and confidential preference', async () => {
  const w = world(); w.render(); await fill(w, 'What do you want to achieve?', 'Secret flower');
  const checkbox = all(w.mount, (n) => n.tagName === 'INPUT')[0]; checkbox.checked = true; await checkbox.emit('change');
  w.routes['POST create'] = () => { throw new Error('network gone'); };
  await btn(w, 'Analyse request').click(); await w.settle(); assert(w.mount.textContent.includes('may have reached'));
  const first = w.calls[0].body; assert.equal(first.confidential, true); assert.equal(field(w, 'What do you want to achieve?').value, 'Secret flower');
  w.routes['POST create'] = envelope(base()); w.routes['POST analyse'] = envelope(base());
  await btn(w, 'Analyse request').click(); await w.settle(); assert.equal(w.calls[1].body.request_id, first.request_id);
  assert.deepEqual(w.calls.map((r) => r.route), ['create', 'create', 'analyse']);
});
test('reconnect fetches the saved intent without resubmitting analysis', async () => {
  const w = world('intent_1'); w.routes['GET view'] = envelope(base()); w.render(); await w.settle();
  assert.deepEqual(w.calls.map((r) => r.route), ['view?id=intent_1']); assert(field(w, 'Clarified request'));
});
test('at most three questions are displayed and why/source wording are literal text', async () => {
  const questions = [1, 2, 3, 4].map((n) => ({ id: 'q' + n, question: 'Which flower ' + n + '?', why: '<img src=x onerror=evil()> changes the drawing.', status: 'pending', blocking: true,
    source_refs: [{ source_id: 'request', start: 0, end: 1, quote: '<script>evil()</script>' }], options: [] }));
  const w = world(); await w.load(envelope(base({ questions })));
  assert.equal(all(w.mount, (n) => n.tagName === 'TEXTAREA' && /^Answer:/.test(n.attrs['aria-label'] || '')).length, 3);
  assert.equal(all(w.mount, (n) => ['SCRIPT', 'IMG'].includes(n.tagName)).length, 0);
  assert(w.mount.textContent.includes('<script>evil()</script>')); assert(w.mount.textContent.includes('More than three questions'));
  assert(btn(w, 'Translate and check').disabled);
});
test('answers survive failed save and carry revision without trusting browser actor', async () => {
  const q = { id: 'q1', question: 'Which colour?', why: 'Changes output.', status: 'pending', blocking: true, options: [] };
  const w = world(); await w.load(envelope(base({ revision: 7, questions: [q] })));
  await fill(w, 'Answer: Which colour?', 'Blue <red>'); w.routes['POST revise'] = { __status: 409 };
  await btn(w, 'Save answer').click(); await w.settle();
  assert.equal(field(w, 'Answer: Which colour?').value, 'Blue <red>');
  const body = w.calls.at(-1).body; assert.equal(body.revision, 7); assert.equal(body.event.kind, 'answer'); assert.equal(body.event.payload.text, 'Blue <red>'); assert(!('actor' in body.event));
});
test('assumption adoption is explicit and translated artifacts are invalidated by returned state', async () => {
  const w = world(); await w.load(envelope(base({ assumptions: [{ id: 'a1', text: 'Five petals', status: 'proposed', consequence: 'Not a photograph' }] })));
  w.routes['POST revise'] = envelope(base({ revision: 2, assumptions: [{ id: 'a1', text: 'Five petals', status: 'adopted' }] }));
  await btn(w, 'Use this assumption').click(); await w.settle(); assert.equal(w.calls.at(-1).body.event.kind, 'assumption');
  assert(w.mount.textContent.includes('adopted')); assert(!w.mount.textContent.includes('intent proven'));
});
test('unsaved rewrite cannot compile or dispatch a previously checked artifact', async () => {
  const a = { source: 'show 1.', inputs: {}, check: { ok: true }, pins: {}, status: 'checked' };
  const w = world(); await w.load(envelope(base({ phase: 'checked' }), { artifact: a }));
  const before = w.calls.length; await fill(w, 'Clarified request', 'Now show 2.');
  assert(btn(w, 'Translate and check').disabled); await btn(w, 'Run on the host').click(); await w.settle();
  assert.equal(w.calls.length, before); assert(w.mount.textContent.includes('Save and check'));
  w.routes['POST revise'] = envelope(base({ revision: 2, revised_prompt: 'Now show 2.' }));
  await btn(w, 'Save clarified request').click(); await w.settle();
  assert.equal(w.calls.at(-1).body.event.kind, 'rewrite'); assert.equal(w.calls.at(-1).body.event.payload.text, 'Now show 2.');
  assert(!all(w.mount, (n) => n.tagName === 'BUTTON' && n.textContent === 'Run on the host').length);
});
test('rewrite conflict keeps local text, refreshing server revision does not erase it', async () => {
  const w = world(); await w.load(envelope(base())); await fill(w, 'Clarified request', 'My revised wording');
  w.routes['POST revise'] = { __status: 409 }; await btn(w, 'Save clarified request').click(); await w.settle();
  assert.equal(field(w, 'Clarified request').value, 'My revised wording');
  w.routes['GET view'] = envelope(base({ revision: 4, revised_prompt: 'Another editor' }));
  await btn(w, 'Refresh saved intent').click(); await w.settle(); assert.equal(field(w, 'Clarified request').value, 'My revised wording');
  assert(btn(w, 'Translate and check').disabled);
});
test('copy uses full readback including original context, and source check is explicitly limited', async () => {
  const w = world(); await w.load(envelope(base({ phase: 'checked' }), { artifact: { source: 'show 1.', check: { ok: true } } }));
  await btn(w, 'Copy rewritten prompt').click(); await w.settle(); assert(w.copied.startsWith('Original:'));
  assert(w.mount.textContent.includes('does not prove it captures everything you meant'));
});
test('handoff needs a checked artifact, starts once, preserves backend mode and only links same-site runner', async () => {
  const w = world(); const a = { source: 'show 1.', check: { ok: true } }; await w.load(envelope(base({ phase: 'checked' }), { artifact: a }));
  w.routes['POST handoff'] = envelope(base({ phase: 'handed_off', revision: 3 }), { artifact: a, handoff: { status: 'done', run_id: 'r1', url: '/runner/#review' } });
  const run = btn(w, 'Run on the host'); await Promise.all([run.click(), run.click()]); await w.settle();
  assert.equal(w.calls.filter((r) => r.route === 'handoff').length, 1); assert(!('mode' in w.calls.at(-1).body));
  assert.equal(all(w.mount, (n) => n.tagName === 'A')[0].attrs.href, '/runner/#review');
  const bad = world(); await bad.load(envelope(base({ phase: 'handed_off' }), { artifact: a, handoff: { status: 'uncertain', url: 'javascript:evil()' } }));
  assert.equal(all(bad.mount, (n) => n.tagName === 'A').length, 0); assert(btn(bad, 'Handoff pending — refresh status').disabled);
});
test('active job polls only GET and preserves failure instead of silently reissuing work', async () => {
  const w = world(); await w.load(envelope(base({ phase: 'draft', goal: '', revised_prompt: '' }), { job: { status: 'running', message: 'Waiting for capacity' } }));
  assert(btn(w, 'Analyse request').disabled); w.routes['GET view'] = envelope(base(), { job: { status: 'failed', message: 'Budget exhausted' } });
  await w.tick(); assert(w.mount.textContent.includes('Budget exhausted')); assert.equal(w.calls.at(-1).method, 'GET'); assert.equal(w.timers.length, 0);
});
test('detaching the tab halts polling and every request disables cache', async () => {
  const w = world(); await w.load(envelope(base(), { job: { status: 'running' } }));
  const before = w.calls.length; w.mount.isConnected = false; await w.tick(); assert.equal(w.calls.length, before);
  assert(w.calls.every((r) => r.opts.cache === 'no-store' && r.opts.credentials === 'same-origin'));
});
test('requirement correction keeps explicit reason and does not bypass unsaved wording', async () => {
  const w = world(); await w.load(envelope(base({ requirements: [{ id: 'r1', text: 'Invented size', kind: 'hard', origin: 'model_extracted', status: 'active' }] })));
  const before = w.calls.length; await btn(w, 'Retire requirement r1').click(); await w.settle(); assert.equal(w.calls.length, before);
  await fill(w, 'Correction reason for r1', 'I did not request this size.');
  w.routes['POST revise'] = envelope(base({ revision: 2, requirements: [{ id: 'r1', text: 'Invented size', status: 'retired' }] }));
  await btn(w, 'Retire requirement r1').click(); await w.settle();
  assert.equal(w.calls.at(-1).body.event.kind, 'requirement'); assert.equal(w.calls.at(-1).body.event.payload.reason, 'I did not request this size.');
});
test('uncertain jobs stay blocked until explicit stop or reconciliation', async () => {
  const w = world(); await w.load(envelope(base(), { job: { status: 'uncertain', message: 'Worker state unknown' } }));
  assert(btn(w, 'Analyse again').disabled); assert(btn(w, 'Translate and check').disabled); assert.equal(w.timers.length, 0);
  w.routes['POST stop'] = envelope(base(), { job: { status: 'failed', message: 'Stopped. Reserved calls remain spent.' } });
  await btn(w, 'Stop interpretation job').click(); await w.settle(); assert.equal(w.calls.at(-1).route, 'stop'); assert(w.mount.textContent.includes('Reserved calls remain spent'));
});
test('stale GET replies never replace a newer content revision', async () => {
  const w = world(); await w.load(envelope(base({ revision: 8, goal: 'New goal' })));
  w.routes['GET view'] = envelope(base({ revision: 3, goal: 'Old goal' })); await btn(w, 'Refresh saved intent').click(); await w.settle();
  assert.equal(field(w, 'Clarified request').value, 'New goal'); assert(w.mount.textContent.includes('Revision 8'));
});
test('clarified editor does not duplicate the full retained context on each rewrite', async () => {
  const w = world(); await w.load(envelope(base({ goal: 'Concise goal', revised_prompt: 'Original: ... plus every decision and source.', turns: [{ kind: 'rewrite', text: 'My concise correction' }] })));
  assert.equal(field(w, 'Clarified request').value, 'My concise correction');
  await fill(w, 'Clarified request', 'One new correction'); await btn(w, 'Copy rewritten prompt').click(); await w.settle(); assert.equal(w.copied, '');
  assert(w.mount.textContent.includes('Save your clarified request'));
});
test('analysis retry keeps operation identity across lost reply and a reconnect', async () => {
  const w = world(); w.render(); await fill(w, 'What do you want to achieve?', 'Make a flower');
  w.routes['POST create'] = envelope(base({ phase: 'draft', goal: '', revised_prompt: '' }));
  w.routes['POST analyse'] = () => { throw new Error('lost reply'); };
  await btn(w, 'Analyse request').click(); await w.settle();
  const original = w.calls.at(-1).body.request_id; assert(original);
  const reconnect = world(w.storage); reconnect.routes['GET view'] = envelope(base({ phase: 'draft', goal: '', revised_prompt: '' })); reconnect.render(); await reconnect.settle();
  reconnect.routes['POST analyse'] = (body) => envelope(base(), { job: { request_id: body.request_id, status: 'failed', message: 'Definite failed job' } });
  await btn(reconnect, 'Analyse request').click(); await reconnect.settle();
  assert.equal(reconnect.calls.at(-1).body.request_id, original);
  await btn(reconnect, 'Analyse again').click(); await reconnect.settle();
  assert.notEqual(reconnect.calls.at(-1).body.request_id, original);
});
test('compile retries retain identity after 500, then explicit retry of a failed job gets a new identity', async () => {
  const w = world(); await w.load(envelope(base())); w.routes['POST compile'] = { __status: 500, error: 'Transient error' };
  await btn(w, 'Translate and check').click(); await w.settle(); const first = w.calls.at(-1).body.request_id;
  w.routes['POST compile'] = (body) => envelope(base(), { job: { status: 'failed', request_id: body.request_id, message: 'Finite compilation failure' } });
  await btn(w, 'Translate and check').click(); await w.settle(); assert.equal(w.calls.at(-1).body.request_id, first);
  await btn(w, 'Translate and check').click(); await w.settle(); assert.notEqual(w.calls.at(-1).body.request_id, first);
});
test('a pending job recovered by GET blocks duplicate work and exposes shared repair allowance', async () => {
  const key = JSON.stringify(['intent_1', 1, 'compile']);
  const w = world({ 'symblic-intent-id': 'intent_1', 'symblic-intent-jobs': JSON.stringify({ [key]: 'pending-identity' }) });
  w.routes['GET view'] = envelope(base(), { job: { request_id: 'pending-identity', status: 'queued' }, budget: { used: 2, limit: 6, repairs_used: 1, repairs_limit: 2 } });
  w.render(); await w.settle(); assert(btn(w, 'Translate and check').disabled); assert(w.mount.textContent.includes('repairs 1 of 2'));
  assert.deepEqual(JSON.parse(w.storage['symblic-intent-jobs']), {}); assert(w.calls.every((r) => r.method === 'GET'));
});
test('older requested-job acknowledgment clears its nonce and keeps the latest job visible', async () => {
  const oldKey = JSON.stringify(['intent_1', 1, 'analyse']), newKey = JSON.stringify(['intent_1', 2, 'compile']);
  const w = world({ 'symblic-intent-id': 'intent_1', 'symblic-intent-jobs': JSON.stringify({ [oldKey]: 'old-analysis', [newKey]: 'new-compile' }) });
  w.routes['GET view'] = envelope(base({ revision: 2 }), { requested_job: { request_id: 'old-analysis', status: 'done' }, job: { request_id: 'new-compile', status: 'running', message: 'Latest compile still running' } });
  w.render(); await w.settle(); const stored = JSON.parse(w.storage['symblic-intent-jobs']);
  assert(!Object.prototype.hasOwnProperty.call(stored, oldKey)); assert.equal(stored[newKey], 'new-compile');
  assert(w.mount.textContent.includes('Latest compile still running')); assert(btn(w, 'Translate and check').disabled);
});
test('handoff reconciliation recovers an existing native run without another handoff dispatch', async () => {
  const a = { source: 'show 1.', check: { ok: true } }; const w = world();
  await w.load(envelope(base({ phase: 'checked' }), { artifact: a, handoff: { status: 'uncertain', message: 'Reply lost' } }));
  w.routes['POST reconcile'] = envelope(base({ phase: 'handed_off' }), { artifact: a, handoff: { status: 'started', run_id: 'old-run', url: '/runner/#run/old-run' } });
  await btn(w, 'Check host handoff').click(); await w.settle();
  assert.equal(w.calls.at(-1).route, 'reconcile'); assert.equal(w.calls.filter((r) => r.route === 'handoff').length, 0);
  assert.equal(all(w.mount, (n) => n.tagName === 'A')[0].attrs.href, '/runner/#run/old-run');
});
test('a failed draft or stale readiness cannot translate even when a readback exists', async () => {
  const w = world(); await w.load(envelope(base({ phase: 'draft', goal: '', revised_prompt: 'Original request retained' }), { job: { status: 'failed', message: 'Catalogue unavailable' }, validation: { ok: true, errors: [], readiness: { phase: 'draft' } } }));
  assert(btn(w, 'Translate and check').disabled); const before = w.calls.length; await btn(w, 'Translate and check').click(); await w.settle(); assert.equal(w.calls.length, before);
  await fill(w, 'Clarified request', 'My additional detail'); assert(btn(w, 'Translate and check').disabled);
});
test('specifics defaults on for new requests, can be readback only, and compile omits the option', async () => {
  const w = world(); w.render(); assert.equal(field(w, 'Ask for specifics').checked, true);
  field(w, 'Ask for specifics').checked = false; await field(w, 'Ask for specifics').emit('change');
  await fill(w, 'What do you want to achieve?', 'Make a flower');
  w.routes['POST create'] = envelope(base()); w.routes['POST analyse'] = envelope(base());
  await btn(w, 'Analyse request').click(); await w.settle();
  assert.equal(w.calls.at(-1).body.require_question, false); assert.equal(field(w, 'Ask for specifics').checked, false);
  w.routes['POST compile'] = envelope(base()); await btn(w, 'Translate and check').click(); await w.settle();
  assert(!Object.prototype.hasOwnProperty.call(w.calls.at(-1).body, 'require_question'));
  await btn(w, 'New interpretation').click(); assert.equal(field(w, 'Ask for specifics').checked, true);
  assert(w.mount.textContent.includes('A question does not prove the interpretation is correct'));
});
test('lost replies keep separate analysis identities for each specifics option across reconnect', async () => {
  const w = world(); await w.load(envelope(base()));
  w.routes['POST analyse'] = () => { throw new Error('lost reply'); };
  await btn(w, 'Analyse again').click(); await w.settle(); const asked = w.calls.at(-1).body;
  assert.equal(asked.require_question, true);
  field(w, 'Ask for specifics').checked = false; await field(w, 'Ask for specifics').emit('change');
  await btn(w, 'Analyse again').click(); await w.settle(); const readback = w.calls.at(-1).body;
  assert.equal(readback.require_question, false); assert.notEqual(asked.request_id, readback.request_id);
  const reconnect = world(w.storage); reconnect.routes['GET view'] = envelope(base()); reconnect.render(); await reconnect.settle();
  assert.equal(field(reconnect, 'Ask for specifics').checked, false);
  reconnect.routes['POST analyse'] = () => { throw new Error('lost again'); };
  await btn(reconnect, 'Analyse again').click(); await reconnect.settle(); assert.equal(reconnect.calls.at(-1).body.request_id, readback.request_id);
  field(reconnect, 'Ask for specifics').checked = true; await field(reconnect, 'Ask for specifics').emit('change');
  await btn(reconnect, 'Analyse again').click(); await reconnect.settle(); assert.equal(reconnect.calls.at(-1).body.request_id, asked.request_id);
});
test('legacy three-part analysis identity is restored only for readback mode', async () => {
  const oldKey = JSON.stringify(['intent_1', 1, 'analyse']);
  const w = world({ 'symblic-intent-id': 'intent_1', 'symblic-intent-jobs': JSON.stringify({ broken: 'ignore', [oldKey]: 'legacy-readback' }) });
  w.routes['GET view'] = envelope(base()); w.render(); await w.settle();
  w.routes['POST analyse'] = () => { throw new Error('lost reply'); };
  await btn(w, 'Analyse again').click(); await w.settle(); assert.notEqual(w.calls.at(-1).body.request_id, 'legacy-readback');
  field(w, 'Ask for specifics').checked = false; await field(w, 'Ask for specifics').emit('change');
  await btn(w, 'Analyse again').click(); await w.settle(); assert.equal(w.calls.at(-1).body.request_id, 'legacy-readback');
  assert.equal(w.calls.at(-1).body.require_question, false);
});
test('answering a clarification switches further analysis to readback and preserves explicit opt-in on reload', async () => {
  const q = { id: 'q1', question: 'Which colour?', status: 'pending', blocking: true, options: [] };
  const w = world(); await w.load(envelope(base({ questions: [q] })));
  assert.equal(field(w, 'Ask for specifics').checked, true);
  await fill(w, 'Answer: Which colour?', 'Blue');
  const answered = envelope(base({ revision: 2, questions: [{ ...q, status: 'answered' }] }));
  w.routes['POST revise'] = answered; await btn(w, 'Save answer').click(); await w.settle();
  assert.equal(field(w, 'Ask for specifics').checked, false); assert.equal(btn(w, 'Translate and check').disabled, false);
  field(w, 'Ask for specifics').checked = true; await field(w, 'Ask for specifics').emit('change');
  const reconnect = world(w.storage); reconnect.routes['GET view'] = answered; reconnect.render(); await reconnect.settle();
  assert.equal(field(reconnect, 'Ask for specifics').checked, true);
  const fresh = world('intent_1'); fresh.routes['GET view'] = answered; fresh.render(); await fresh.settle();
  assert.equal(field(fresh, 'Ask for specifics').checked, false);
});
test('busy and uncertain jobs lock the specifics option without changing an in-flight request', async () => {
  const w = world(); await w.load(envelope(base()));
  let finish; w.routes['POST analyse'] = () => new Promise((resolve) => { finish = resolve; });
  const click = btn(w, 'Analyse again').click(); await w.settle();
  const option = field(w, 'Ask for specifics'); assert.equal(option.disabled, true);
  option.checked = false; await option.emit('change'); assert.equal(w.calls.at(-1).body.require_question, true);
  finish(envelope(base(), { job: { status: 'uncertain' } })); await click; await w.settle();
  assert.equal(field(w, 'Ask for specifics').disabled, true); assert.equal(field(w, 'Ask for specifics').checked, true);
});
test('deterministic recipe can return checked readback without a question even with specifics requested', async () => {
  const w = world(); await w.load(envelope(base({ goal: 'List offline nodes', questions: [] }), { budget: { used: 0, limit: 6 }, job: { status: 'done', mechanism: 'deterministic_recipe_match' } }));
  assert.equal(w.calls.at(-1).body.require_question, true); assert.equal(btn(w, 'Translate and check').disabled, false);
  assert(w.mount.textContent.includes('Built-in workflows can proceed directly'));
});
test('failed requested refinement keeps checked source but blocks compile and new handoff until analysis succeeds', async () => {
  const artifact = { source: 'show 1.', inputs: {}, check: { ok: true } };
  const failed = envelope(base({ phase: 'checked' }), { artifact,
    job: { status: 'failed', kind: 'analyse', require_question: true, message: 'Question generation failed' },
    validation: { ok: true, errors: [], readiness: { phase: 'checked', analysis_required: true } } });
  const w = world(); await w.load(failed);
  assert(btn(w, 'Translate and check').disabled); assert(btn(w, 'Run on the host').disabled);
  assert(w.mount.textContent.includes('show 1.')); assert(field(w, 'Clarified request').value);
  assert(w.mount.textContent.includes('Requested clarification did not finish. Retry analysis, or turn off Ask for specifics and analyse for a read-back.'));
  const before = w.calls.length; await btn(w, 'Translate and check').click(); await btn(w, 'Run on the host').click(); await w.settle(); assert.equal(w.calls.length, before);
  field(w, 'Ask for specifics').checked = false; await field(w, 'Ask for specifics').emit('change');
  assert(btn(w, 'Translate and check').disabled); assert(btn(w, 'Run on the host').disabled);
  w.routes['POST analyse'] = envelope(base({ revision: 2, phase: 'checked' }), { artifact,
    job: { status: 'done' }, validation: { ok: true, errors: [], readiness: { phase: 'checked', analysis_required: false } } });
  await btn(w, 'Analyse again').click(); await w.settle(); assert.equal(w.calls.at(-1).body.require_question, false);
  assert.equal(btn(w, 'Translate and check').disabled, false); assert.equal(btn(w, 'Run on the host').disabled, false);
  assert(!w.mount.textContent.includes('Requested clarification did not finish'));
});
test('an analysis-required hold preserves access to an existing native run', async () => {
  const w = world(); await w.load(envelope(base({ phase: 'handed_off' }), {
    artifact: { source: 'show 1.', check: { ok: true } }, handoff: { status: 'started', run_id: 'existing', url: '/runner/#run/existing' },
    validation: { ok: true, errors: [], readiness: { phase: 'handed_off', analysis_required: true } }, job: { status: 'failed' } }));
  assert(btn(w, 'Translate and check').disabled);
  assert.equal(all(w.mount, (n) => n.tagName === 'A')[0].attrs.href, '/runner/#run/existing');
  assert(!all(w.mount, (n) => n.tagName === 'BUTTON' && n.textContent === 'Run on the host').length);
});
test('stale runtime pins block a new run while allowing explicit retranslation', async () => {
  const artifact = { source: 'show 1.', inputs: {}, check: { ok: true } };
  const w = world(); await w.load(envelope(base({ phase: 'checked' }), { artifact,
    artifact_compatibility: { status: 'stale', differences: ['kernel', 'modules'], message: 'The checked runtime changed.' } }));
  assert(btn(w, 'Run on the host').disabled); assert.equal(btn(w, 'Translate and check').disabled, false);
  assert(w.mount.textContent.includes('Translate and check again')); assert(w.mount.textContent.includes('Changed: kernel, modules.'));
  assert(w.mount.textContent.includes('show 1.')); const before = w.calls.length;
  await btn(w, 'Run on the host').click(); await w.settle(); assert.equal(w.calls.length, before);
  w.routes['POST compile'] = envelope(base({ phase: 'checked', revision: 2 }), { artifact,
    artifact_compatibility: { status: 'current', differences: [], message: '' } });
  await btn(w, 'Translate and check').click(); await w.settle();
  assert.equal(btn(w, 'Run on the host').disabled, false); assert.equal(w.calls.at(-1).route, 'compile');
});
test('stale or unknown runtime metadata never hides an existing native handle', async () => {
  for (const status of ['stale', 'unknown']) {
    const w = world(); await w.load(envelope(base({ phase: 'handed_off' }), {
      artifact: { source: 'show 1.', check: { ok: true } }, artifact_compatibility: { status, differences: [], message: 'Metadata unavailable' },
      handoff: { status: 'started', run_id: 'earlier', url: '/runner/#run/earlier' } }));
    assert.equal(all(w.mount, (n) => n.tagName === 'A')[0].attrs.href, '/runner/#run/earlier');
    assert.equal(btn(w, 'Translate and check').disabled, true);
    assert(w.mount.textContent.includes('Revise the request or create a new interpretation'));
  }
});
test('an earlier content revision keeps its run link without blocking the revised translation', async () => {
  const w = world(); await w.load(envelope(base({ phase: 'checked', content_revision: 3 }), {
    artifact: { source: 'show 1.', check: { ok: true } },
    artifact_compatibility: { status: 'current', differences: [] },
    handoff: { content_revision: 2, status: 'started', run_id: 'earlier', url: '/runner/#run/earlier' } }));
  assert.equal(all(w.mount, (n) => n.tagName === 'A')[0].attrs.href, '/runner/#run/earlier');
  assert.equal(btn(w, 'Translate and check').disabled, false);
  assert.equal(btn(w, 'Run on the host').disabled, false);
});
test('rewriting before another translation keeps the previous native run visible', async () => {
  const w = world(); await w.load(envelope(base({ phase: 'specified', content_revision: 3 }), {
    artifact: null, handoff: { content_revision: 2, status: 'started', run_id: 'earlier', url: '/runner/#run/earlier' } }));
  assert.equal(all(w.mount, (n) => n.tagName === 'A')[0].attrs.href, '/runner/#run/earlier');
  assert(w.mount.textContent.includes('Earlier host handoff'));
  assert.equal(btn(w, 'Translate and check').disabled, false);
});
test('unknown compatibility explains the hold while older missing metadata preserves server validation', async () => {
  const artifact = { source: 'show 1.', check: { ok: true } };
  const w = world(); await w.load(envelope(base({ phase: 'checked' }), { artifact,
    artifact_compatibility: { status: 'unknown', differences: [], message: 'Catalogue temporarily unavailable' } }));
  assert(btn(w, 'Run on the host').disabled); assert.equal(btn(w, 'Translate and check').disabled, false);
  assert(w.mount.textContent.includes('Current compatibility could not be checked')); assert(w.mount.textContent.includes('Catalogue temporarily unavailable'));
  const old = world(); await old.load(envelope(base({ phase: 'checked' }), { artifact }));
  assert.equal(btn(old, 'Run on the host').disabled, false); assert(old.mount.textContent.includes('not reported by this API'));
  assert(!old.mount.textContent.includes('Translation matches the current runtime'));
  const malformed = world(); await malformed.load(envelope(base({ phase: 'checked' }), { artifact, artifact_compatibility: { status: 'proven' } }));
  assert(btn(malformed, 'Run on the host').disabled);
});
test('retranslation eligibility does not bypass the earlier requested-clarification hold', async () => {
  const w = world(); await w.load(envelope(base({ phase: 'checked' }), {
    artifact: { source: 'show 1.', check: { ok: true } }, artifact_compatibility: { status: 'stale', differences: ['kernel'] },
    validation: { ok: true, errors: [], readiness: { phase: 'checked', analysis_required: true } } }));
  assert(btn(w, 'Translate and check').disabled); assert(btn(w, 'Run on the host').disabled);
});
test('evidence distinguishes owner decisions, source correspondence, static checks and proposed examples', async () => {
  const quote = '<script>outside()</script> is source wording';
  const w = world(); await w.load(envelope(base({ assumptions: [{ id: 'a1', text: 'Owner adopted assumption', status: 'adopted', source_refs: [{ source_id: 'request', start: 0, end: 42, quote }] }],
    questions: [{ id: 'q1', status: 'answered' }], examples: [{ text: 'Illustrative example', kind: 'positive' }] }), {
    job: { status: 'done', evidence: { observation: {}, question_check: 'presence_only', feedback_exposed: true, independence: 'not_established' } },
    artifact: { source: 'show 1.', check: { ok: true }, checks: [{ kind: 'static', ok: true, scope: 'Syntax only' }, { kind: 'effect_static', ok: false, scope: 'Missing capability' }] } }));
  const evidence = all(w.mount, (n) => n.tagName === 'DETAILS' && n.className.includes('si-evidence'))[0];
  assert(evidence); assert(evidence.textContent.includes('Model proposal')); assert(evidence.textContent.includes('presence, not its usefulness'));
  assert(evidence.textContent.includes('earlier rejected answer')); assert(evidence.textContent.includes('independence is not established'));
  assert(evidence.textContent.includes('1 answered clarification; 1 adopted assumption')); assert(evidence.textContent.includes('not observed facts'));
  assert(evidence.textContent.includes(quote)); assert.equal(all(evidence, (n) => n.tagName === 'SCRIPT').length, 0);
  assert(evidence.textContent.includes('Language and input checks · passed · Syntax only')); assert(evidence.textContent.includes('Declared capability checks · failed · Missing capability'));
  assert(evidence.textContent.includes('Requirements are retained; the static map and observed execution checks are shown separately.'));
  assert(evidence.textContent.includes('1 proposed example')); assert(evidence.textContent.includes('have not been executed by this view'));
  assert(evidence.textContent.includes('Executed predicate or mathematical checks belong to the host run'));
});
test('missing evidence and unknown check kinds cannot become truth claims; summaries are bounded', async () => {
  const w = world(); await w.load(envelope(base({ assumptions: Array.from({ length: 8 }, (_, n) => ({ id: 'a' + n, status: 'adopted', text: 'A'.repeat(1000) })) }), {
    artifact: { source: 'show 1.', check: { ok: true }, checks: [{ kind: 'unrecognized', scope: 'Unknown scope' }] } }));
  const evidence = all(w.mount, (n) => n.tagName === 'DETAILS' && n.className.includes('si-evidence'))[0];
  assert(evidence.textContent.includes('Analysis mechanism unavailable')); assert(evidence.textContent.includes('Question-check evidence unavailable'));
  assert(evidence.textContent.includes('Other receipt: unrecognized · result unavailable')); assert(evidence.textContent.includes('First 6 adopted assumptions'));
  assert.equal(all(evidence, (n) => n.className === 'si-evidence-quote').length, 6);
  assert(!evidence.textContent.includes('A'.repeat(502))); assert(!evidence.textContent.includes('100%'));
});
test('contradictory or malformed compatibility cannot claim current or enable a new run', async () => {
  for (const differences of [['kernel'], 'kernel', undefined, ['unrecognized'], Array(7).fill('kernel')]) {
    const w = world(); await w.load(envelope(base({ phase: 'checked' }), {
      artifact: { source: 'show 1.', check: { ok: true } }, artifact_compatibility: { status: 'current', differences } }));
    assert(btn(w, 'Run on the host').disabled); assert.equal(btn(w, 'Translate and check').disabled, false);
    assert(w.mount.textContent.includes('Current compatibility could not be checked'));
    assert(!w.mount.textContent.includes('Translation matches the current runtime'));
    assert(!w.mount.textContent.includes('Changed: kernel.'));
    const before = w.calls.length; await btn(w, 'Run on the host').click(); await w.settle(); assert.equal(w.calls.length, before);
  }
});
test('owner predicate editor preserves the requirement and submits one revisioned expression', async () => {
  const w = world(); const requirements = [{id:'r-total',text:'Use the total.',kind:'hard',status:'active',origin:'model_extracted',predicate:null}];
  await w.load(envelope(base({revision:4, requirements})));
  await fill(w, 'Check expression for r-total', 'total = 120');
  w.routes['POST revise'] = envelope(base({revision:5,requirements:[{...requirements[0],predicate:'total = 120'}]}));
  await btn(w, 'Save check expression r-total').click(); await w.settle();
  const body = w.calls.at(-1).body;
  assert.equal(body.revision,4); assert.equal(body.event.kind,'predicate');
  assert.deepEqual(body.event.payload,{requirement_id:'r-total',predicate:'total = 120'});
  assert(!('actor' in body.event)); assert(w.mount.textContent.includes('Use the total.'));
});
test('coverage shows all missing obligations and does not call a present predicate executed', async () => {
  const w=world();
  await w.load(envelope(base({phase:'checked',requirements:[{id:'r1',text:'Exact total',kind:'hard',status:'active'},{id:'r2',text:'Preserve exception',kind:'hard',status:'active'}]}), {
    artifact:{source:'if false then\n assert total = 120.\nend.',check:{ok:true},coverage:{version:1,scope:'declared_predicate_presence_only',unmapped_hard_ids:['r2'],requirements:[
      {id:'r1',status:'predicate_present',reason:'Reachability is unassessed.',locations:[{kind:'assert',line:2,col:2}]},
      {id:'r2',status:'unmapped',reason:'No declared predicate.',locations:[]}],examples:[{id:'e1',kind:'negative'}]}}
  }));
  assert(w.mount.textContent.includes('Hard requirements without a declared-predicate match: r2.'));
  assert(w.mount.textContent.includes('Predicate present; execution not assessed by this map.'));
  assert(w.mount.textContent.includes('1 negative cases. None is reported as an executed or held-out test.'));
  assert(w.mount.textContent.includes('assert at line 2, column 2'));
});
test('coverage attributes an owner predicate only when origin is recorded', async () => {
  const w=world();
  await w.load(envelope(base({phase:'checked'}), {artifact:{source:'assert true.',check:{ok:true},coverage:{version:2,scope:'declared_predicate_presence_only',requirements:[
    {id:'owner',status:'predicate_present',predicate_origin:'owner_declared',locations:[]},
    {id:'model',status:'proposed_predicate_present',predicate_origin:'model_proposed',locations:[]},
    {id:'legacy',status:'predicate_present',locations:[]}],examples:[]}}}));
  assert(w.mount.textContent.includes('Owner-declared predicate present; execution not assessed by this map.'));
  assert(w.mount.textContent.includes('Model-proposed predicate present; requirement remains unmapped.'));
  assert(w.mount.textContent.includes('Predicate present; execution not assessed by this map.'));
});
test('source attachment is preserved through the create request and visible after analysis', async () => {
  const w=world(); w.render();
  await fill(w,'What do you want to achieve?','Read this invoice.');
  await fill(w,'Reference text (optional)','Invoice <script>literal</script> total USD 120.');
  const state=base({sources:[{id:'reference-1',kind:'document',text:'Invoice <script>literal</script> total USD 120.',sha256:'a'.repeat(64)}]});
  w.routes['POST create']=envelope(state);w.routes['POST analyse']=envelope(state);
  await btn(w,'Analyse request').click();await w.settle();
  assert.equal(w.calls[0].body.sources[0].text,'Invoice <script>literal</script> total USD 120.');
  assert(w.mount.textContent.includes('Retained source documents'));
  assert(w.mount.textContent.includes('Invoice <script>literal</script> total USD 120.'));
  assert.equal(all(w.mount,n=>n.tagName==='SCRIPT').length,0);
});
test('execution coverage separates observed retained checks from dead or ambiguous mappings', async () => {
  const w=world();
  const c={version:1,scope:'linked_run_retained_encoded_checks',status:'joined',run_status:'failed',binding:{run_id:'abcdef123456'},requirements:[
    {id:'pass',status:'observed_pass',passed_checks:2,failed_checks:0,mapping_status:'predicate_present'},
    {id:'fail',status:'observed_fail',passed_checks:0,failed_checks:1,mapping_status:'proposed_predicate_present'},
    {id:'dead',status:'unobserved',passed_checks:0,failed_checks:0},
    {id:'ambiguous',status:'ambiguous',passed_checks:0,failed_checks:0}]};
  await w.load(envelope(base({phase:'handed_off'}),{artifact:{source:'assert true.',check:{ok:true}},execution_coverage:c,
    handoff:{status:'started',run_id:'abcdef123456',url:'/runner/#run/abcdef123456',content_revision:1}}));
  assert(w.mount.textContent.includes('pass · Observed passing encoded checks'));
  assert(w.mount.textContent.includes('fail · Observed failing encoded checks'));
  assert(w.mount.textContent.includes('2 passing; 0 failing retained checks.'));
  assert(w.mount.textContent.includes('dead · No retained check observation'));
  assert(w.mount.textContent.includes('Location attribution ambiguous'));
  assert(w.mount.textContent.includes('This is a model-proposed predicate; the requirement remains unmapped.'));
  assert(w.mount.textContent.includes('does not establish intended meaning, owner acceptance, or external truth'));
  assert.equal(all(w.mount,n=>n.tagName==='BUTTON' && n.textContent==='Run on the host').length,0);
  assert.deepEqual(w.calls.map(r=>r.route),['create','analyse']);
});
test('stale or partial evidence never renders prior successful counts as current observations', async () => {
  for (const status of ['stale','partial','unknown']) {
    const w=world();
    await w.load(envelope(base({phase:'checked'}),{artifact:{source:'assert true.',check:{ok:true}},execution_coverage:{
      version:1,scope:'linked_run_retained_encoded_checks',status,requirements:[{id:'old',status:'observed_pass',passed_checks:99,failed_checks:0}]}}));
    const section=all(w.mount,n=>n.tagName==='SECTION' && n.children.some(c=>c.tagName==='H3' && c.textContent==='Observed execution checks'))[0];
    assert(section.textContent.includes('Unassessed for this saved run'));
    assert(!section.textContent.includes('99 passing'));
    assert(!section.textContent.includes('Observed passing encoded checks'));
  }
});
test('malformed execution coverage does not break the interpreter or relax readiness', async () => {
  const w=world();
  await w.load(envelope(base({phase:'specified'}),{artifact:{source:'assert true.',check:{ok:true}},execution_coverage:{version:1,scope:'wrong',status:'joined',requirements:[]}}));
  assert(w.mount.textContent.includes('Executed requirement checks are unavailable in this reply.'));
  assert(btn(w,'Run on the host').disabled);
});
test('malformed execution coverage rows cannot crash rendering', async () => {
  for (const row of [null,false,[],{id:'r',status:null}]) {
    const w=world();
    await w.load(envelope(base(),{artifact:{source:'assert true.',check:{ok:true}},execution_coverage:{version:1,
      scope:'linked_run_retained_encoded_checks',status:'joined',requirements:[row]}}));
    assert(w.mount.textContent.includes('Executed requirement checks are unavailable in this reply.'));
  }
});
(async () => {
  for (const [name, fn] of cases) { await fn(); process.stdout.write('PASS ' + name + '\n'); }
  process.stdout.write(cases.length + ' journeys passed\n');
})().catch((e) => { console.error(e); process.exitCode = 1; });
