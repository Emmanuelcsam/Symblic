// Intercept every API and disable WebSocket before scripts; no models, shell or stores touched.
import {before, after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {test, launch, open, axe, noHorizontalScroll} from './host-harness.mjs';
let browser;
before(async () => { browser = await launch(); });
after(async () => { await browser?.close(); });
const ENGINES = ['triad', 'gpt', 'gemini', 'claude', 'codex', 'agy', 'copilot', 'local', 'council', 'squad'];
const CATALOG = {
  specs: Object.fromEntries(ENGINES.map(id => [id, {title: id, blurb: id === 'triad' ? 'Pick who sits in each seat (ChatGPT and Antigravity unless you change them).' : id + ' tools', efforts: id === 'codex' ? ['', 'low', 'high'] : []}])),
  models: Object.fromEntries(ENGINES.map(id => [id, id === 'local' ? [{id: 'qwen3:4b-instruct', title: 'Qwen 4B'}, {id: 'llama3.2:1b', title: 'Llama 1B'}] : [{id: id + '-model', title: id + ' model'}]])),
  machines: {local: 'host', engines: ['codex', 'claude', 'triad', 'local', 'gpt', 'gemini']},
  nodes: [{id: 'host', label: 'host', local: true, online: true, ready: {codex: true}, models: [{name: 'qwen3:4b-instruct'}]},
    {id: 'node-a', label: 'Node A', online: true, probed: true, ready: {codex: true, triad: true}, models: [{name: 'qwen3:8b'}]},
    {id: 'node-b', label: 'Node B', online: false, probed: false, ready: {}, models: []}],
  seats: Object.fromEntries(['mastermind', 'implementer', 'ai_review'].map(id => [id, [{id: 'ollama', title: 'Ollama'}, {id: 'codex', title: 'Codex'}]])),
  seatEngine: {ollama: 'local', codex: 'codex'}, seatEfforts: {ollama: [''], codex: ['', 'high']}, home: '/fixture/project'
};
const TASK = {id: 'fixture-task', status: 'active', instruction: 'Build a snake game.', options: {engine: 'codex', node: 'node-a'},
  steps: [{index: 0, instruction: 'Build a snake game.', status: 'active', agent_id: 'fixture-agent', url: '/terminal?session=fixture-agent&node=node-a', screen: '<img src=x onerror="window.xss=1">'}]};
async function boot({mobile = false, routes = {}, storage = '', url = '/symblic-terminal.html'} = {}) {
  const fixture = async (request, url) => {
    if (routes[url.pathname]) return routes[url.pathname](request, url);
    if (url.pathname === '/api/symblicos/catalog') return {json: CATALOG};
    if (url.pathname === '/api/symblicos/tasks') return {json: {tasks: []}};
    if (url.pathname === '/api/symblicos/tasks/start') return {json: {task: TASK}};
    if (url.pathname === '/api/symblicos/tasks/get') return {json: {task: TASK}};
    if (url.pathname === '/api/symblicos/tasks/control') return {json: {task: {...TASK, status: 'cancelled'}}};
    if (url.pathname === '/api/agents/dirs') return {json: {path: '/fixture/project', parent: '/fixture', dirs: [{name: 'games', path: '/fixture/project/games'}]}};
    if (url.pathname === '/api/agents/council/templates') return {json: {templates: [{id: 'panel', title: 'Panel', spec: {stages: [{kind: 'propose', members: [{engine: 'ollama', model: 'qwen3:4b-instruct', node: 'node-a', count: 3}]}]}}]}};
    if (url.pathname === '/api/runner/engines') return {json: {engines: [{spec: 'ollama:qwen3:8b@node-a', engine: 'ollama', model: 'qwen3:8b', title: 'Qwen 8B', typed_ask: true, ready: true}, {spec: 'claude:sonnet@node-a', engine: 'claude', model: 'sonnet', kind: 'cli', title: 'Claude', typed_ask: true, ready: true}], errors: []}};
    if (url.pathname === '/api/automation/symblic/meta') return {json: {version: 'fixture', examples: [], features: {}}};
    if (url.pathname === '/api/automation/symblic/english/examples') return {json: {examples: {simple: {source: 'Remember selected is 7.\nShow selected.', title: 'Simple'}}}};
    if (url.pathname === '/api/automation/symblic/editor/check') { const body = request.postDataJSON(); return {json: {version: 1, language: 'english', source_length_utf16: body.source.length, available: true, ok: true, diagnostics: [], check: {ok: true}}}; }
    return {json: {}};
  };
  // The folder is never pre-filled from the catalogue's home any more (a task in ~ silently edits the wrong
  // tree, 2026-10-10): the journeys start as a returning user whose saved draft already names the folder.
  const seeded = storage || `if (!sessionStorage.getItem('symblic-task-composer-v1')) sessionStorage.setItem('symblic-task-composer-v1', JSON.stringify({draft: {cwd: '/fixture/project'}}));`;
  return open(browser, url, fixture, {mobile, storage: `window.WebSocket = class { static CONNECTING=0; static OPEN=1; static CLOSING=2; static CLOSED=3; constructor(){this.readyState=3;} addEventListener(){} removeEventListener(){} send(){} close(){} }; ${seeded}`,
    files: {'/terminal': {body: '<!doctype html><title>Fixture shell</title><p>Fixture shell only</p>', contentType: 'text/html'}}});
}
async function ready(s) { await s.page.getByLabel('Agent', {exact: true}).locator('option').filter({hasText: 'codex'}).waitFor({state: 'attached'}); }
async function draft(s, instruction = 'Build a snake game.') {
  await ready(s);
  await s.page.getByLabel('Your instruction', {exact: true}).fill(instruction);
  await s.page.getByLabel('Agent', {exact: true}).selectOption('codex');
  await s.page.getByLabel('Model', {exact: true}).selectOption('codex-model');
  await s.page.getByLabel('Effort', {exact: true}).selectOption('high');
  await s.page.getByLabel('Machine', {exact: true}).selectOption('node-a');
}
for (const mobile of [false, true]) test(`direct command, exact catalogue and safe output (${mobile ? 'phone dark' : 'desktop light'})`, async () => {
  const s = await boot({mobile});
  try {
    await draft(s);
    await s.page.evaluate(dark => Studio.setTheme(dark ? 'dark' : 'light'), mobile);
    assert.equal(await s.page.getByLabel('Agent', {exact: true}).locator('option').count(), ENGINES.length);
    assert.equal(await s.page.getByLabel('Agent', {exact: true}).locator('option[value="gpt"]').textContent(), 'ChatGPT (web)');
    assert.equal(s.requests.find(row => row.path === '/api/symblicos/catalog').search, '');
    await s.page.getByRole('button', {name: 'Refresh agents', exact: true}).click();
    await s.page.waitForFunction(() => [...document.querySelectorAll('.st-composer button')].some(button => button.textContent === 'Refresh agents' && !button.disabled));
    assert.equal(s.requests.filter(row => row.path === '/api/symblicos/catalog').at(-1).search, '?refresh=1');
    assert.equal(s.requests.filter(row => row.method === 'POST' && row.path.startsWith('/api/symblicos/')).length, 0);
    assert.equal(await s.page.locator('iframe').count(), 0);
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.locator('[data-task-id="fixture-task"]').waitFor();
    const writes = s.requests.filter(row => row.path.endsWith('tasks/start'));
    assert.equal(writes.length, 1);
    assert.equal(writes[0].body.instruction, 'Build a snake game.');
    assert.equal(writes[0].body.node, 'node-a'); assert.equal(writes[0].body.model, 'codex-model'); assert.equal(writes[0].body.effort, 'high');
    assert.equal(writes[0].body.cwd, '/fixture/project'); assert.equal(writes[0].body.worktree, false);
    await s.page.getByText('Agent output', {exact: true}).click();
    assert.equal(await s.page.locator('[data-st-tasks] img').count(), 0);
    assert.equal(await s.page.evaluate(() => window.xss), undefined);
    assert.equal(await noHorizontalScroll(s.page), true);
    if (process.env.SYMBLIC_TERMINAL_SHOTS) { await mkdir(process.env.SYMBLIC_TERMINAL_SHOTS, {recursive: true}); await s.page.screenshot({path: `${process.env.SYMBLIC_TERMINAL_SHOTS}/${mobile ? 'phone-dark' : 'desktop-light'}.png`, fullPage: true}); }
    assert.deepEqual(await axe(s.page), []);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});
test('fresh lines retain exact instructions and explicit context; cancellation is a saved control', async () => {
  const s = await boot();
  try {
    await draft(s, 'Create a project.\n\nBuild a game.\nTest it.');
    await s.page.getByLabel('Mode', {exact: true}).selectOption('lines');
    await s.page.getByText('Folder, context and execution', {exact: true}).click();
    await s.page.getByLabel('Shared context for each fresh task').fill('Use only this project.');
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.locator('[data-task-id="fixture-task"]').waitFor();
    const body = s.requests.find(row => row.path.endsWith('tasks/start')).body;
    assert.equal(body.mode, 'lines'); assert.equal(body.context_note, 'Use only this project.');
    assert.equal(body.instruction, 'Create a project.\n\nBuild a game.\nTest it.');
    await s.page.getByRole('button', {name: 'Cancel task', exact: true}).click();
    await s.page.getByText('cancelled', {exact: true}).waitFor();
    assert.deepEqual(s.requests.find(row => row.path.endsWith('tasks/control')).body, {id: 'fixture-task', action: 'cancel'});
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});
test('actual workspace and node distinguish remote results from the source folder', async () => {
  const source = '/fixture/source/project';
  const workspace = '/fixture/remote/agents-work/execute-instruction-20261006';
  const remoteTask = {...TASK, status: 'completed', workspace,
    options: {...TASK.options, node: 'auto', cwd: source},
    steps: TASK.steps.map(step => ({...step, status: 'completed', agent: {node: 'node-a', cwd: '/fixture/remote/initial-checkout'}}))};
  const s = await boot({mobile: true, routes: {'/api/symblicos/tasks': () => ({json: {tasks: [remoteTask]}})}});
  try {
    await ready(s);
    const card = s.page.locator('[data-task-id="fixture-task"]');
    await card.getByText('Execution workspace: node-a · ' + workspace, {exact: true}).waitFor();
    assert.equal(await card.getByText('Source folder: ' + source, {exact: true}).isVisible(), true);
    assert.equal(await card.getByText(/Changes stay in the execution workspace until you review and apply them/).isVisible(), true);
    assert.equal(await card.getByRole('link', {name: 'Review / apply work ↗', exact: true}).getAttribute('href'), '/agents.html#work');
    assert.equal((await card.textContent()).includes('/fixture/remote/initial-checkout'), false);
    assert.equal(await s.page.locator('iframe').count(), 0);
    await s.page.route('**/files.html', route => route.fulfill({body: '<!doctype html><title>Fixture files</title>', contentType: 'text/html'}));
    await s.page.getByRole('button', {name: 'Files', exact: true}).click();
    await s.page.getByText(/Browse and edit files on the dashboard host/).waitFor();
    assert.equal(await noHorizontalScroll(s.page), true);
    assert.deepEqual(s.requests.filter(row => row.method === 'POST' && row.path !== '/api/perf/beacon').map(row => row.path), []);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});
test('initial unprobed fleet refreshes once, preserves choices, and stops watching after one minute', async () => {
  let reads = 0;
  const saved = {draft: {mode: 'qwen', engine: 'triad', model: 'qwen3:remote-fixture', node: 'node-a', cwd: '/fixture/project',
    instruction: 'Keep this exact instruction.', roles: {mastermind: 'ollama', mastermind_model: 'qwen3:remote-fixture'}}};
  const s = await boot({storage: `sessionStorage.setItem('symblic-task-composer-v1', ${JSON.stringify(JSON.stringify(saved))});`,
    routes: {'/api/symblicos/catalog': () => {
      reads++;
      return {json: {...CATALOG, nodes: [CATALOG.nodes[0],
        {...CATALOG.nodes[1], probed: reads >= 4, ready: reads >= 4 ? {triad: true} : {triad: false},
          notes: {triad: 'not installed'}, models: reads >= 4 ? [{name: 'qwen3:remote-fixture'}] : []},
        {...CATALOG.nodes[2], online: true, probed: false}]}};
    }}});
  try {
    await ready(s);
    await s.page.getByText(/Refresh requested; node metadata updates as probes finish/).waitFor();
    // Reload under a controlled clock so the complete watch interval needs no real-minute wait.
    await s.page.clock.install({time: new Date('2026-10-06T12:00:00Z')});
    await s.page.clock.pauseAt(new Date('2026-10-06T12:00:01Z'));
    reads = 0; s.requests.length = 0;
    await s.page.reload(); await ready(s);
    await s.page.getByText(/Refresh requested; node metadata updates as probes finish/).waitFor();
    assert.equal(await s.page.getByLabel('Machine', {exact: true}).locator('option:checked').textContent(), 'Node A · availability unknown');
    assert.equal(await s.page.getByText('Machine metadata has not been checked yet; cached readiness is unknown.', {exact: false}).isVisible(), true);
    for (let poll = 0; poll < 2; poll++) {
      const response = s.page.waitForResponse(r => new URL(r.url()).pathname === '/api/symblicos/catalog');
      await s.page.clock.runFor(5000);
      await (await response).finished();
      await s.page.getByText(/10 agent types · 3 machines/).waitFor();
    }
    const model = s.page.getByLabel('Model', {exact: true});
    assert.equal(await model.inputValue(), 'qwen3:remote-fixture');
    assert.equal(await model.locator('option:checked').textContent(), 'qwen3:remote-fixture');
    assert.equal(await s.page.getByLabel('Planner model', {exact: true}).inputValue(), 'qwen3:remote-fixture');
    assert.equal(await s.page.getByLabel('Machine', {exact: true}).inputValue(), 'node-a');
    assert.equal(await s.page.getByLabel('Your instruction', {exact: true}).inputValue(), 'Keep this exact instruction.');
    const finalResponse = s.page.waitForResponse(r => new URL(r.url()).pathname === '/api/symblicos/catalog');
    await s.page.clock.fastForward(60000);
    await (await finalResponse).finished();
    await s.page.getByText(/Some machine metadata is still unknown. Use Refresh agents to check again./).waitFor();
    const catalogueRequests = () => s.requests.filter(row => row.path === '/api/symblicos/catalog');
    assert.equal(catalogueRequests().filter(row => row.search === '?refresh=1').length, 1);
    const settledCount = catalogueRequests().length;
    await s.page.clock.runFor(120000);
    assert.equal(catalogueRequests().length, settledCount);
    assert.deepEqual(s.requests.filter(row => row.method === 'POST' && row.path !== '/api/perf/beacon').map(row => row.path), []);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});
test('uncertain submit locks exact payload and retry reuses id, including after reload', async () => {
  let calls = 0;
  const s = await boot({routes: {'/api/symblicos/tasks/start': () => ++calls === 1 ? {abort: true} : {json: {task: TASK, duplicate: true}}}});
  try {
    await draft(s);
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.getByRole('button', {name: 'Reconnect this submission', exact: true}).waitFor();
    assert.equal(await s.page.getByLabel('Your instruction', {exact: true}).isDisabled(), true);
    await s.page.reload(); await ready(s);
    await s.page.getByRole('button', {name: 'Reconnect this submission', exact: true}).click();
    await s.page.locator('[data-task-id="fixture-task"]').waitFor();
    const bodies = s.requests.filter(row => row.path.endsWith('tasks/start')).map(row => row.body);
    assert.equal(bodies.length, 2); assert.deepEqual(bodies[0], bodies[1]);
    assert.equal(await s.page.getByLabel('Your instruction', {exact: true}).isDisabled(), false);
  } finally { await s.context.close(); }
});
test('Three Qwen selects real roles and fleet model without hiding machine choice', async () => {
  const s = await boot();
  try {
    await s.page.setViewportSize({width: 1365, height: 900});
    await ready(s);
    const primaryActionAboveAdvanced = async () => {
      const runBox = await s.page.getByRole('button', {name: 'Run instruction', exact: true}).boundingBox();
      const advancedBox = await s.page.getByText('Folder, context and execution', {exact: true}).boundingBox();
      assert.ok(runBox && advancedBox && runBox.y + runBox.height <= advancedBox.y);
      assert.ok(runBox.y >= 0 && runBox.y + runBox.height <= 900, 'primary action remains in the initial desktop viewport');
      assert.equal(await noHorizontalScroll(s.page), true);
    };
    await s.page.getByLabel('Agent', {exact: true}).selectOption('triad');
    await s.page.getByText(/ChatGPT and Antigravity unless you change them/).waitFor();
    await primaryActionAboveAdvanced();
    await s.page.getByLabel('Mode', {exact: true}).selectOption('qwen');
    assert.equal(await s.page.getByText(/ChatGPT and Antigravity unless you change them/).count(), 0);
    await s.page.getByText(/All three seats use Ollama with fresh role contexts/).waitFor();
    await primaryActionAboveAdvanced();
    await s.page.getByLabel('Model', {exact: true}).selectOption('qwen3:8b');
    await s.page.getByLabel('Machine', {exact: true}).selectOption('node-a');
    await s.page.getByLabel('Your instruction', {exact: true}).fill('Build, critique, then fix a snake game.');
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.locator('[data-task-id="fixture-task"]').waitFor();
    const body = s.requests.find(row => row.path.endsWith('tasks/start')).body;
    assert.equal(body.mode, 'qwen'); assert.equal(body.engine, 'triad'); assert.equal(body.model, 'qwen3:8b'); assert.equal(body.node, 'node-a');
    assert.equal(Object.hasOwn(body, 'fresh_lines'), false);
    assert.deepEqual(body.roles, {mastermind: 'ollama', implementer: 'ollama', ai_review: 'ollama'});
  } finally { await s.context.close(); }
});
test('Three Qwen can start a fresh team for each exact input line', async () => {
  const s = await boot();
  try {
    await ready(s);
    assert.equal(await s.page.getByLabel('New team for each line', {exact: true}).isVisible(), false);
    await s.page.getByLabel('Mode', {exact: true}).selectOption('qwen');
    const fresh = s.page.getByLabel('New team for each line', {exact: true});
    assert.equal(await fresh.isChecked(), false);
    await fresh.check();
    await s.page.getByLabel('Model', {exact: true}).selectOption('qwen3:8b');
    await s.page.getByLabel('Machine', {exact: true}).selectOption('node-a');
    const instruction = ' Create a retro Snake game.\n\nReview and test its movement. ';
    await s.page.getByLabel('Your instruction', {exact: true}).fill(instruction);
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.locator('[data-task-id="fixture-task"]').waitFor();
    const body = s.requests.find(row => row.path.endsWith('tasks/start')).body;
    assert.equal(body.instruction, instruction);
    assert.equal(body.mode, 'qwen'); assert.equal(body.fresh_lines, true);
    assert.equal(Object.hasOwn(body.roles, 'fresh_lines'), false);
    assert.deepEqual(body.roles, {mastermind: 'ollama', implementer: 'ollama', ai_review: 'ollama'});
  } finally { await s.context.close(); }
});
test('mode changes clear incompatible model choices while preserving exact Qwen selection', async () => {
  const s = await boot();
  try {
    await draft(s);
    await s.page.getByLabel('Mode', {exact: true}).selectOption('qwen');
    assert.equal(await s.page.getByLabel('Model', {exact: true}).inputValue(), '');
    assert.equal(await s.page.getByLabel('Effort', {exact: true}).inputValue(), '');
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.getByText('Choose an installed Qwen model.', {exact: true}).waitFor();
    assert.equal(s.requests.filter(row => row.path.endsWith('tasks/start')).length, 0);
    await s.page.getByLabel('Model', {exact: true}).selectOption('qwen3:8b');
    await s.page.getByLabel('New team for each line', {exact: true}).check();
    await s.page.getByLabel('Mode', {exact: true}).selectOption('agent');
    assert.equal(await s.page.getByLabel('Model', {exact: true}).inputValue(), '');
    assert.equal(await s.page.getByLabel('New team for each line', {exact: true}).isVisible(), false);
    await s.page.getByLabel('Agent', {exact: true}).selectOption('local');
    await s.page.getByLabel('Model', {exact: true}).selectOption('qwen3:4b-instruct');
    await s.page.getByLabel('Mode', {exact: true}).selectOption('qwen');
    assert.equal(await s.page.getByLabel('Model', {exact: true}).inputValue(), 'qwen3:4b-instruct');
    assert.equal(await s.page.getByLabel('New team for each line', {exact: true}).isChecked(), true);
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.locator('[data-task-id="fixture-task"]').waitFor();
    const body = s.requests.find(row => row.path.endsWith('tasks/start')).body;
    assert.equal(body.model, 'qwen3:4b-instruct'); assert.equal(body.fresh_lines, true);
    assert.equal(body.effort, '');
  } finally { await s.context.close(); }
});
test('missing saved engine remains explicit and can recover after choosing an available agent', async () => {
  const saved = {draft: {engine: 'removed-engine', model: 'saved-model', instruction: 'Create a game.', node: 'host', cwd: '/fixture/project'}};
  const s = await boot({storage: `sessionStorage.setItem('symblic-task-composer-v1', ${JSON.stringify(JSON.stringify(saved))});`});
  try {
    await ready(s);
    assert.equal(await s.page.getByLabel('Agent', {exact: true}).inputValue(), 'removed-engine');
    assert.equal(await s.page.getByLabel('Model', {exact: true}).inputValue(), 'saved-model');
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.getByText('The selected agent is absent from the current catalogue. Refresh agents or choose an available agent.', {exact: true}).waitFor();
    assert.equal(s.requests.filter(row => row.path.endsWith('tasks/start')).length, 0);
    await s.page.getByLabel('Agent', {exact: true}).selectOption('codex');
    assert.equal(await s.page.getByLabel('Model', {exact: true}).inputValue(), '');
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.locator('[data-task-id="fixture-task"]').waitFor();
    assert.equal(s.requests.find(row => row.path.endsWith('tasks/start')).body.engine, 'codex');
  } finally { await s.context.close(); }
});
test('native tools load only on click, preserve shell iframe when collapsed', async () => {
  const s = await boot();
  try {
    await ready(s); await s.page.getByLabel('Machine', {exact: true}).selectOption('node-a');
    assert.equal(await s.page.locator('iframe').count(), 0);
    await s.page.getByRole('button', {name: 'Shell', exact: true}).click();
    const frame = s.page.getByTitle('Shell workspace', {exact: true});
    assert.equal(await frame.getAttribute('src'), '/terminal?node=node-a');
    await s.page.getByRole('button', {name: 'Close Shell', exact: true}).click();
    assert.equal(await frame.count(), 1); assert.equal(await frame.isVisible(), false);
    await s.page.getByRole('button', {name: 'Shell', exact: true}).click(); assert.equal(await frame.isVisible(), true);
    assert.equal(s.requests.filter(row => row.method === 'POST' && row.path.startsWith('/api/symblicos/')).length, 0);
  } finally { await s.context.close(); }
});
test('English exposes complete tool-agent catalogue and discovered typed statement choices', async () => {
  const s = await boot({url: '/automation-studio/symblic.html#english'});
  try {
    await s.page.locator('#sy-en-source').waitFor();
    await s.page.locator('[data-en-panel=limits] > summary').click();
    await s.page.locator('#sy-en-by option[value="ollama:qwen3:8b@node-a"]').waitFor({state: 'attached'});
    await s.page.locator('#sy-en-by').selectOption('claude:sonnet@node-a');
    assert.equal(await s.page.locator('#sy-en-by').inputValue(), 'claude:sonnet@node-a');
    await s.page.locator('#sy-en-execution').selectOption('agent');
    await ready(s);
    assert.equal(await s.page.getByLabel('Agent', {exact: true}).locator('option').count(), ENGINES.length);
    assert.equal(await s.page.locator('#sy-en-source').count(), 1);
    assert.equal(s.requests.some(row => row.path.endsWith('tasks/start')), false);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});

test('bounded OS commands retain legacy receipts and never run on opening', async () => {
  let writes = 0;
  const s = await boot({routes: {
    '/api/symblicos/vitals': () => ({json: {hostname: 'fixture-host', filesystem_root: '/fixture/os-files'}}),
    '/api/symblicos/terminal/submit': request => { writes++; return {json: {receipt: {execution_id: 'exec-fixture', original_instruction: request.postDataJSON().instruction, result_status: 'success', stdout: 'Created fixture file.'}}}; },
    '/api/symblicos/terminal/history': () => ({json: {history: []}})
  }});
  try {
    await s.page.getByRole('button', {name: 'OS commands', exact: true}).click();
    await s.page.getByText(/OS file workspace: \/fixture\/os-files/).waitFor();
    assert.equal(writes, 0);
    await s.page.getByLabel('Bounded OS instruction').fill('Create a text file named "note.txt".');
    await s.page.getByRole('button', {name: 'Run OS command', exact: true}).click();
    await s.page.getByText('Created fixture file.', {exact: true}).waitFor();
    assert.equal(writes, 1);
    assert.equal(s.requests.filter(row => row.path.endsWith('tasks/start')).length, 0);
    assert.deepEqual(s.errors, []);
  } finally { await s.context.close(); }
});

test('task screen and manual next use the durable task API', async () => {
  const reviewed = {...TASK, status: 'awaiting_review', screen: 'Fresh bounded terminal output', resume_required: false,
    steps: [{...TASK.steps[0], screen: undefined, status: 'awaiting_review'}, {index: 1, instruction: 'Test it.', status: 'queued'}]};
  const s = await boot({routes: {'/api/symblicos/tasks': () => ({json: {tasks: [reviewed]}})}});
  try {
    await s.page.getByText('Running · manual finish', {exact: true}).waitFor();
    await s.page.getByText('Agent may still be working. Inspect the result; Finish stops this step before advancing.', {exact: true}).waitFor();
    await s.page.getByText('Agent output', {exact: true}).click();
    await s.page.getByText('Fresh bounded terminal output', {exact: true}).waitFor();
    await s.page.getByRole('button', {name: 'Finish step & Next', exact: true}).click();
    await s.page.getByText('cancelled', {exact: true}).waitFor();
    assert.deepEqual(s.requests.find(row => row.path.endsWith('tasks/control')).body, {id: 'fixture-task', action: 'next'});
  } finally { await s.context.close(); }
});

test('new project supplies managed cwd before dispatch and reuses name after uncertain creation', async () => {
  let creates = 0;
  const s = await boot({routes: {'/api/symblicos/workspace/create': request => {
    creates++;
    assert.equal(request.postDataJSON().name, 'snake-game');
    return creates === 1 ? {abort: true} : {json: {cwd: '/fixture/projects/snake-game', name: 'snake-game', created: false, baseline: 'fixture'}};
  }}});
  try {
    await draft(s);
    await s.page.getByText('Folder, context and execution', {exact: true}).click();
    await s.page.getByRole('button', {name: 'New project', exact: true}).click();
    await s.page.getByLabel('New project name', {exact: true}).fill('snake-game');
    await s.page.getByRole('button', {name: 'Create project', exact: true}).click();
    await s.page.getByRole('alert').waitFor();
    await s.page.getByRole('button', {name: 'Create project', exact: true}).click();
    await s.page.getByText(/Existing managed project: \/fixture\/projects\/snake-game/).waitFor();
    assert.equal(await s.page.getByLabel('Working folder', {exact: true}).inputValue(), '/fixture/projects/snake-game');
    await s.page.getByRole('button', {name: 'Run instruction', exact: true}).click();
    await s.page.locator('[data-task-id="fixture-task"]').waitFor();
    assert.equal(s.requests.find(row => row.path.endsWith('tasks/start')).body.cwd, '/fixture/projects/snake-game');
    assert.equal(creates, 2);
  } finally { await s.context.close(); }
});
