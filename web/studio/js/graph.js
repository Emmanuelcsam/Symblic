// Draws the automation canvas graph (nodes, links, connect mode). Imports ./state.js, which is not part of this
// repository: the canvas is kept for reference (see web/README.md).
import { state, selectedId } from './state.js';
import { NODE_HELP } from './constants.js';
import { escapeHtml } from './utils.js';

let nodesEl;
let linksEl;
let onSelect = () => {};
let onConnect = () => {};
let connectMode = false;
let connectFrom = null;
let drag = null;

export function initGraph({ nodesElement, linksElement, onNodeSelect, onEdgeConnect }) {
  nodesEl = nodesElement;
  linksEl = linksElement;
  onSelect = onNodeSelect;
  onConnect = onEdgeConnect;
  nodesEl.addEventListener('click', () => {
    if (!connectMode) {
      onSelect(null);
    }
  });
}

export function setConnectMode(enabled) {
  connectMode = enabled;
  connectFrom = null;
}

export function renderGraph() {
  if (!nodesEl || !linksEl) return;
  nodesEl.innerHTML = '';
  Object.values(state.graph.nodes).forEach(node => {
    const el = document.createElement('div');
    el.className = 'node' + (node.id === selectedId ? ' selected' : '');
    el.style.left = node.x + 'px';
    el.style.top = node.y + 'px';
    el.dataset.id = node.id;
    const helpText = buildNodeHelp(node);
    if (helpText) {
      el.dataset.help = helpText;
    }
    const prompt = getNodeSummary(node);
    const summary = prompt ? escapeHtml(prompt.slice(0, 60)) : ' ';
    el.innerHTML = `
      <header>${escapeHtml(node.type.toUpperCase())}</header>
      <div class="title">${escapeHtml(node.title || node.type)}</div>
      <div class="subtitle">${summary}</div>
    `;
    el.addEventListener('mousedown', startDrag);
    el.addEventListener('click', handleNodeClick);
    nodesEl.appendChild(el);
  });
  renderEdges();
}

function getNodeSummary(node) {
  const data = node.data || {};
  if (node.type === 'ollama') return data.prompt || '';
  if (node.type === 'email') return data.subject || data.to || '';
  if (node.type === 'websearch') return data.query || '';
  if (node.type === 'webfetch') return data.url || '';
  if (node.type === 'readfile') return data.path || '';
  if (node.type === 'writefile') return data.path || '';
  if (node.type === 'schedule') {
    const listPreview = data.scheduleList ? String(data.scheduleList).split('\n')[0] : '';
    return data.runAt || data.recurrence || listPreview || '';
  }
  if (node.type === 'delay') return data.seconds ? `${data.seconds}s` : '';
  if (node.type === 'context') return `${data.action || 'clear'} ${data.contextKey || ''}`.trim();
  if (node.type === 'setvar') return data.key || '';
  if (node.type === 'log') return data.path || '';
  if (node.type === 'email_reply') return data.mailbox || '';
  if (node.type === 'loop') return data.count ? `x${data.count}` : 'infinite';
  if (node.type === 'python_script') return data.scriptPath || data.functionName || '';
  if (node.type === 'agent') return `${data.by || 'claude:haiku'} · ${data.prompt || ''}`;
  if (node.type === 'council') return `${data.template || 'panel'} · ${data.prompt || ''}`;
  if (node.type === 'triad') return data.task || '';
  if (node.type === 'symblic') return (String(data.source || '').match(/^\s*program\s*:?\s*(.+)$/im) || [])[1] || 'program';
  return '';
}

function buildNodeHelp(node) {
  const baseHelp = NODE_HELP[node.type] || '';
  const details = buildNodeDetails(node);
  if (baseHelp && details) {
    return `${baseHelp}\n\nCurrent settings:\n${details}`;
  }
  return baseHelp || details;
}

function buildNodeDetails(node) {
  const data = node.data || {};
  const lines = [];
  if (node.title) lines.push(`Title: ${clipValue(node.title)}`);
  switch (node.type) {
    case 'ollama':
      if (data.provider) lines.push(`Provider: ${clipValue(data.provider)}`);
      if (data.model) lines.push(`Model: ${clipValue(data.model)}`);
      if (data.outputMode) lines.push(`Output: ${clipValue(data.outputMode)}`);
      break;
    case 'email':
      if (data.to) lines.push(`To: ${clipValue(data.to)}`);
      if (data.subject) lines.push(`Subject: ${clipValue(data.subject)}`);
      break;
    case 'websearch':
      if (data.query) lines.push(`Query: ${clipValue(data.query)}`);
      if (data.maxResults) lines.push(`Max results: ${clipValue(String(data.maxResults))}`);
      break;
    case 'webfetch':
      if (data.url) lines.push(`URL: ${clipValue(data.url)}`);
      if (data.maxChars) lines.push(`Max chars: ${clipValue(String(data.maxChars))}`);
      break;
    case 'readfile':
      if (data.path) lines.push(`Path: ${clipValue(data.path)}`);
      if (data.maxChars) lines.push(`Max chars: ${clipValue(String(data.maxChars))}`);
      break;
    case 'writefile':
      if (data.path) lines.push(`Path: ${clipValue(data.path)}`);
      if (data.mode) lines.push(`Mode: ${clipValue(data.mode)}`);
      break;
    case 'schedule':
      if (data.runAt) lines.push(`Run at: ${clipValue(data.runAt)}`);
      if (data.recurrence) lines.push(`Recurrence: ${clipValue(data.recurrence)}`);
      if (data.scheduleMode) lines.push(`Mode: ${clipValue(data.scheduleMode)}`);
      break;
    case 'delay':
      if (data.seconds) lines.push(`Seconds: ${clipValue(String(data.seconds))}`);
      break;
    case 'context':
      if (data.action) lines.push(`Action: ${clipValue(data.action)}`);
      if (data.contextKey) lines.push(`Key: ${clipValue(data.contextKey)}`);
      break;
    case 'setvar':
      if (data.key) lines.push(`Key: ${clipValue(data.key)}`);
      if (data.mode) lines.push(`Mode: ${clipValue(data.mode)}`);
      break;
    case 'email_reply':
      if (data.mailbox) lines.push(`Mailbox: ${clipValue(data.mailbox)}`);
      if (data.limit) lines.push(`Limit: ${clipValue(String(data.limit))}`);
      break;
    case 'log':
      if (data.path) lines.push(`Log path: ${clipValue(data.path)}`);
      break;
    case 'python_script':
      if (data.scriptPath) lines.push(`Script: ${clipValue(data.scriptPath)}`);
      if (data.functionName) lines.push(`Function: ${clipValue(data.functionName)}`);
      if (data.outputVar) lines.push(`Output var: ${clipValue(data.outputVar)}`);
      break;
    case 'agent':
      lines.push(`Agent: ${clipValue(data.by || 'claude:haiku')}`);
      if (data.effort) lines.push(`Effort: ${clipValue(data.effort)}`);
      break;
    case 'council':
      lines.push(`Council: ${clipValue(data.template || 'panel')}`);
      break;
    case 'symblic':
      if (data.by) lines.push(`Default agent: ${clipValue(data.by)}`);
      break;
    case 'loop':
      if (data.count !== undefined && data.count !== '') lines.push(`Count: ${clipValue(String(data.count))}`);
      if (data.delaySeconds) lines.push(`Delay: ${clipValue(String(data.delaySeconds))}s`);
      break;
    default:
      break;
  }
  return lines.join('\n');
}

function clipValue(value, max = 56) {
  const text = String(value);
  if (text.length <= max) return text;
  return text.slice(0, Math.max(0, max - 3)) + '...';
}

function handleNodeClick(e) {
  e.stopPropagation();
  const id = e.currentTarget.dataset.id;
  if (connectMode) {
    if (!connectFrom) {
      connectFrom = id;
      onConnect({ mode: 'from', from: id });
    } else if (connectFrom !== id) {
      onConnect({ mode: 'to', from: connectFrom, to: id });
      connectFrom = null;
    }
    return;
  }
  onSelect(id);
}

function startDrag(e) {
  const id = e.currentTarget.dataset.id;
  const node = state.graph.nodes[id];
  if (!node) return;
  drag = { id, offsetX: e.offsetX, offsetY: e.offsetY };
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', endDrag);
}

function onDrag(e) {
  if (!drag) return;
  const node = state.graph.nodes[drag.id];
  if (!node) return;
  const rect = nodesEl.getBoundingClientRect();
  node.x = e.clientX - rect.left - drag.offsetX;
  node.y = e.clientY - rect.top - drag.offsetY;
  renderGraph();
}

function endDrag() {
  if (!drag) return;
  drag = null;
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', endDrag);
}

function renderEdges() {
  linksEl.innerHTML = '';
  linksEl.setAttribute('width', '100%');
  linksEl.setAttribute('height', '100%');
  const svgNS = 'http://www.w3.org/2000/svg';
  state.graph.edges.forEach(edge => {
    const fromNode = state.graph.nodes[edge.from];
    const toNode = state.graph.nodes[edge.to];
    if (!fromNode || !toNode) return;
    const x1 = fromNode.x + 140;
    const y1 = fromNode.y + 40;
    const x2 = toNode.x + 30;
    const y2 = toNode.y + 40;
    const path = document.createElementNS(svgNS, 'path');
    const dx = (x2 - x1) * 0.5;
    const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
    path.setAttribute('d', d);
    path.classList.add('edge-path');
    linksEl.appendChild(path);
    if (edge.label) {
      const label = document.createElementNS(svgNS, 'text');
      label.setAttribute('x', (x1 + x2) / 2);
      label.setAttribute('y', (y1 + y2) / 2 - 6);
      label.classList.add('edge-label');
      label.textContent = edge.label;
      linksEl.appendChild(label);
    }
  });
}
