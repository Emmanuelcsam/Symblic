// The canvas's Symblic text-mode panel: parses the editor text with ./symblic/parser.js, shows the plan and compiles
// the workflow with ./symblic/compiler.js, then sends it to the host (POST /api/automation/compile). Needs the host's
// canvas page; the parser and compiler themselves are pure (tests/browser/symblic-studio-text-mode.mjs).
import { DEFAULT_SOURCE } from './symblic/constants.js';
import { collectSettings, applySettings, normalizeDefaults } from './symblic/settings.js';
import { parseSymblic } from './symblic/parser.js';
import { buildWorkflow } from './symblic/compiler.js';
import { buildPlanItems } from './symblic/plan.js';

const DRAFT_KEY = 'symblicDraft';
const SETTINGS_KEY = 'symblicSettings';
const STUDIO_KEY = 'symblicWorkflow';

const sourceEl = document.getElementById('symblicSource');
const planEl = document.getElementById('symblicPlan');
const warningsEl = document.getElementById('symblicWarnings');
const statusEl = document.getElementById('symblicStatus');
const draftStatusEl = document.getElementById('symblicDraftStatus');
const jsonEl = document.getElementById('symblicJson');

const elements = {
  workflowNameEl: document.getElementById('symblicWorkflowName'),
  providerEl: document.getElementById('symblicProvider'),
  modelEl: document.getElementById('symblicModel'),
  systemEl: document.getElementById('symblicSystem'),
  responseStyleEl: document.getElementById('symblicResponseStyle'),
  defaultContextModeEl: document.getElementById('symblicDefaultContextMode'),
  contextKeyEl: document.getElementById('symblicContextKey'),
  contextScopeEl: document.getElementById('symblicContextScope'),
  outputModeEl: document.getElementById('symblicOutputMode'),
  maxMessagesEl: document.getElementById('symblicMaxMessages'),
  maxCharsEl: document.getElementById('symblicMaxChars'),
  maxTokensEl: document.getElementById('symblicMaxTokens'),
  contextWindowEl: document.getElementById('symblicContextWindow'),
  temperatureEl: document.getElementById('symblicTemperature'),
  fileInputsEl: document.getElementById('symblicFileInputs'),
  fileMaxCharsEl: document.getElementById('symblicFileMaxChars')
};

const exampleBtn = document.getElementById('symblicExample');
const compileBtn = document.getElementById('symblicCompile');
const copyBtn = document.getElementById('symblicCopy');
const downloadBtn = document.getElementById('symblicDownload');
const sendBtn = document.getElementById('symblicSend');
const saveBtn = document.getElementById('symblicSave');

// Server-side compile (automation_engine.compile_symblic is a verbatim port of
// the parser+compiler in this folder). Saving here makes the text program a
// real workflow the scheduler can run headlessly, with no canvas round-trip.
function handleServerSave() {
  const settings = collectSettings(elements);
  if (statusEl) statusEl.textContent = 'Compiling on the server...';
  fetch('/api/automation/compile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source: sourceEl ? sourceEl.value : '',
      settings,
      save: true,
      name: settings.workflowName || ''
    })
  }).then(r => r.json()).then(resp => {
    if (!statusEl) return;
    if (resp.error) {
      statusEl.textContent = resp.error + ' (a 404 here means the host '
        + 'service has not been restarted yet)';
      return;
    }
    const item = resp.item || {};
    statusEl.textContent = 'Saved as "' + (item.name || 'workflow') + '" ('
      + (resp.stats ? resp.stats.steps : '?') + ' steps, '
      + (resp.warnings || []).length + ' warning(s)). Open it from Studio \u203a Load.';
  }).catch(err => {
    if (statusEl) statusEl.textContent = 'Server compile failed: ' + (err.message || err);
  });
}

function loadSettings() {
  const raw = localStorage.getItem(SETTINGS_KEY);
  if (!raw) return;
  try {
    const settings = JSON.parse(raw);
    applySettings(elements, settings);
  } catch (err) {
    console.warn('Failed to load settings', err);
  }
}

function saveSettings() {
  const settings = collectSettings(elements);
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

function loadDraft() {
  const stored = localStorage.getItem(DRAFT_KEY);
  if (stored) {
    sourceEl.value = stored;
    return;
  }
  sourceEl.value = DEFAULT_SOURCE;
}

function saveDraft() {
  localStorage.setItem(DRAFT_KEY, sourceEl.value);
  if (draftStatusEl) {
    draftStatusEl.textContent = 'Draft saved';
  }
}

function renderPlanItems(statements) {
  const items = buildPlanItems(statements || []);
  if (!items.length) {
    planEl.textContent = 'No steps yet.';
    return;
  }
  planEl.innerHTML = '';
  items.forEach(item => {
    const row = document.createElement('div');
    row.className = 'plan-item';
    row.style.marginLeft = `${item.depth * 14}px`;

    const meta = document.createElement('div');
    meta.className = 'plan-meta';
    meta.textContent = item.meta;

    const title = document.createElement('div');
    title.className = 'plan-prompt';
    title.textContent = item.title;

    row.appendChild(meta);
    row.appendChild(title);
    planEl.appendChild(row);
  });
}

function renderWarnings(warnings) {
  if (!warnings.length) {
    warningsEl.textContent = 'No warnings.';
    return;
  }
  warningsEl.innerHTML = '';
  warnings.forEach(warn => {
    const row = document.createElement('div');
    row.className = 'warning';
    const title = document.createElement('strong');
    title.textContent = `Line ${warn.line}`;
    const msg = document.createElement('span');
    msg.textContent = warn.message;
    row.appendChild(title);
    row.appendChild(msg);
    warningsEl.appendChild(row);
  });
}

function updateOutput() {
  const settings = collectSettings(elements);
  const defaults = normalizeDefaults(settings);
  const parsed = parseSymblic(sourceEl.value || '', defaults);
  const workflow = buildWorkflow(parsed, settings);

  jsonEl.value = JSON.stringify(workflow, null, 2);
  renderPlanItems(parsed.statements);
  renderWarnings(parsed.warnings);

  const statusParts = [`${parsed.stats.steps} steps`];
  if (parsed.stats.blocks) statusParts.push(`${parsed.stats.blocks} blocks`);
  if (parsed.warnings.length) statusParts.push(`${parsed.warnings.length} warnings`);
  statusEl.textContent = statusParts.join(' | ');
}

function handleCopy() {
  if (!jsonEl.value) return;
  navigator.clipboard.writeText(jsonEl.value).then(() => {
    statusEl.textContent = 'Workflow JSON copied.';
  }).catch(() => {
    statusEl.textContent = 'Copy failed. Select the JSON and copy manually.';
  });
}

function handleDownload() {
  if (!jsonEl.value) return;
  const blob = new Blob([jsonEl.value], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `symblic-workflow-${Date.now()}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  statusEl.textContent = 'Downloaded workflow JSON.';
}

function handleSend() {
  if (!jsonEl.value) {
    statusEl.textContent = 'No workflow to send. Compile first.';
    return;
  }
  try {
    // Validate JSON before storing
    const parsed = JSON.parse(jsonEl.value);
    if (!parsed.graph || typeof parsed.graph !== 'object') {
      throw new Error('Invalid workflow: missing graph');
    }
    localStorage.setItem(STUDIO_KEY, jsonEl.value);
    statusEl.textContent = 'Sent to Studio. Redirecting...';
    setTimeout(() => {
      window.location.href = 'index.html';
    }, 100);
  } catch (err) {
    statusEl.textContent = `Failed to send: ${err.message || 'Invalid workflow JSON'}`;
  }
}

function attachListeners() {
  if (sourceEl) {
    sourceEl.addEventListener('input', () => {
      saveDraft();
      updateOutput();
    });
  }

  Object.values(elements).forEach(el => {
    if (!el) return;
    const handler = () => {
      saveSettings();
      updateOutput();
    };
    el.addEventListener('input', handler);
    el.addEventListener('change', handler);
  });

  if (exampleBtn) {
    exampleBtn.addEventListener('click', () => {
      sourceEl.value = DEFAULT_SOURCE;
      saveDraft();
      updateOutput();
    });
  }

  if (compileBtn) compileBtn.addEventListener('click', () => updateOutput());
  if (copyBtn) copyBtn.addEventListener('click', handleCopy);
  if (downloadBtn) downloadBtn.addEventListener('click', handleDownload);
  if (sendBtn) sendBtn.addEventListener('click', handleSend);
  if (saveBtn) saveBtn.addEventListener('click', handleServerSave);
}

loadSettings();
loadDraft();
attachListeners();
updateOutput();
if (draftStatusEl) {
  draftStatusEl.textContent = 'Draft ready';
}
