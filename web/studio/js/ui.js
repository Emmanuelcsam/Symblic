// The automation canvas controller: toolbars, templates, history, runs and schedules. It imports canvas modules
// that are not part of this repository and calls the host's /api/automation/ routes; kept for reference.
import { NODE_TYPES } from './constants.js';
import { state, addNode, addEdge, removeNode, replaceState, setSelectedId, selectedId } from './state.js';
import { renderGraph, initGraph, setConnectMode } from './graph.js';
import { renderInspector } from './inspector.js';
import { renderEdgesList } from './edges.js';
import { TEMPLATES, buildTemplateGraph } from './templates.js';
import { initHistory } from './history.js';
import { apiGet, apiPost, setApiBase, getApiBase } from './api.js';
import { HELP_TEXT, TEMPLATE_HELP } from './help.js';
import { initScriptLibrary } from './scripts.js';
import { initPipelineBuilder, derivePipelineSteps } from './pipeline.js';

// Canvas state for zoom/pan
const canvasState = {
  zoom: 100,
  snapToGrid: false,
  gridSize: 28
};

export function initUI() {
  // Declared up here on purpose: renderAll() -> syncPipelineFromGraph()
  // runs long before initPipelineBuilder() is reached, and a `const`
  // down there put this identifier in the temporal dead zone — reading it
  // threw 'Cannot access pipelineBuilder before initialization' out of the
  // first render, which killed initUI and with it the whole Studio.
  let pipelineBuilder = null;
  const nodesEl = document.getElementById('nodes');
  const linksEl = document.getElementById('links');
  const inspector = document.getElementById('inspectorContent');
  const nodeButtons = document.getElementById('nodeButtons');
  const templateList = document.getElementById('templateList');
  const edgesList = document.getElementById('edgesList');
  const workflowSelect = document.getElementById('workflowSelect');
  const autosaveStatus = document.getElementById('autosaveStatus');
  const quickActions = document.getElementById('quickActions');
  const quickActionStatus = document.getElementById('quickActionStatus');
  const methodButtons = document.getElementById('methodButtons');
  const autoConnectNodes = document.getElementById('autoConnectNodes');
  const runModeStatus = document.getElementById('runModeStatus');

  const runBtn = document.getElementById('runWorkflow');
  const stopBtn = document.getElementById('stopRun');
  const saveBtn = document.getElementById('saveWorkflow');
  const newBtn = document.getElementById('newWorkflow');
  const connectBtn = document.getElementById('connectMode');
  const deleteBtn = document.getElementById('deleteNode');
  const apiBaseInput = document.getElementById('apiBaseInput');
  const apiBaseSave = document.getElementById('apiBaseSave');
  const apiStatus = document.getElementById('apiStatus');
  const runHistory = document.getElementById('runHistory');
  const scriptSearch = document.getElementById('scriptSearch');
  const scriptCategory = document.getElementById('scriptCategory');
  const scriptView = document.getElementById('scriptView');
  const scriptList = document.getElementById('scriptList');
  const scriptDetails = document.getElementById('scriptDetails');
  const scriptAddNode = document.getElementById('scriptAddNode');
  const scriptOpenCode = document.getElementById('scriptOpenCode');
  const scriptEdit = document.getElementById('scriptEdit');
  const scriptReload = document.getElementById('scriptReload');
  const scriptsDirInput = document.getElementById('scriptsDirInput');
  const scriptsDirApply = document.getElementById('scriptsDirApply');
  const scriptEditor = document.getElementById('scriptEditor');
  const scriptEditorText = document.getElementById('scriptEditorText');
  const scriptEditorSave = document.getElementById('scriptEditorSave');
  const scriptEditorReload = document.getElementById('scriptEditorReload');
  const scriptEditorClose = document.getElementById('scriptEditorClose');
  const scriptEditorStatus = document.getElementById('scriptEditorStatus');
  const pipelineList = document.getElementById('pipelineList');
  const pipelineDetails = document.getElementById('pipelineDetails');
  const pipelineAddStep = document.getElementById('pipelineAddStep');
  const pipelineRemoveStep = document.getElementById('pipelineRemoveStep');
  const pipelineClear = document.getElementById('pipelineClear');
  const pipelineApply = document.getElementById('pipelineApply');
  const pipelineExport = document.getElementById('pipelineExport');
  const pipelineImport = document.getElementById('pipelineImport');
  const pipelineImportFile = document.getElementById('pipelineImportFile');
  const pipelineReplace = document.getElementById('pipelineReplace');
  const pipelineSync = document.getElementById('pipelineSync');
  const pipelineStatus = document.getElementById('pipelineStatus');

  const runLog = document.getElementById('runLog');
  const lastOutput = document.getElementById('lastOutput');

  // Canvas tools elements
  const canvasZoom = document.getElementById('canvasZoom');
  const zoomOut = document.getElementById('zoomOut');
  const zoomIn = document.getElementById('zoomIn');
  const zoomReset = document.getElementById('zoomReset');
  const zoomFit = document.getElementById('zoomFit');
  const zoomSelection = document.getElementById('zoomSelection');
  const autoLayout = document.getElementById('autoLayout');
  const gridToggle = document.getElementById('gridToggle');
  const snapToggle = document.getElementById('snapToggle');
  const easyModeToggle = document.getElementById('easyModeToggle');
  const themeSelect = document.getElementById('themeSelect');
  const canvasStatus = document.getElementById('canvasStatus');
  const canvas = document.getElementById('canvas');
  const nodesContainer = document.getElementById('nodes');

  // Node navigator elements
  const nodeSearch = document.getElementById('nodeSearch');
  const nodeCount = document.getElementById('nodeCount');
  const nodeList = document.getElementById('nodeList');

  // Workflow tools elements
  const workflowName = document.getElementById('workflowName');
  const renameWorkflow = document.getElementById('renameWorkflow');
  const duplicateWorkflow = document.getElementById('duplicateWorkflow');
  const exportWorkflowJson = document.getElementById('exportWorkflowJson');
  const importWorkflowJson = document.getElementById('importWorkflowJson');
  const importWorkflowFile = document.getElementById('importWorkflowFile');
  const workflowToolStatus = document.getElementById('workflowToolStatus');

  // Command palette elements
  const commandPalette = document.getElementById('commandPalette');
  const paletteClose = document.getElementById('paletteClose');
  const paletteInput = document.getElementById('paletteInput');
  const paletteList = document.getElementById('paletteList');

  const renderAll = () => {
    renderGraph();
    renderInspector(inspector, () => {
      renderGraph();
      renderEdgesList(edgesList, () => {
        renderGraph();
        setStatus('Unsaved');
      });
      setStatus('Unsaved');
    });
    renderEdgesList(edgesList, () => {
      renderGraph();
      setStatus('Unsaved');
    });
    syncPipelineFromGraph();
    // Update node navigator
    if (typeof renderNodeNavigator === 'function') {
      renderNodeNavigator();
    }
    // Update workflow name
    if (workflowName) {
      workflowName.value = state.name || '';
    }
  };

  function setStatus(text) {
    autosaveStatus.textContent = text;
  }

  function setHelp(el, text) {
    if (!el || !text) return;
    el.dataset.help = text;
    const wrap = el.closest('.field');
    if (wrap) {
      const label = wrap.querySelector('label');
      if (label) label.dataset.help = text;
    }
    const parentLabel = el.closest('label');
    if (parentLabel) parentLabel.dataset.help = text;
  }

  function applyHelpText() {
    Object.entries(HELP_TEXT).forEach(([id, text]) => {
      const el = document.getElementById(id);
      setHelp(el, text);
    });
  }

  function maybeAutoConnect(prevId, newId) {
    if (!autoConnectNodes || !autoConnectNodes.checked) return;
    if (!prevId || !newId || prevId === newId) return;
    const prevNode = state.graph.nodes[prevId];
    if (prevNode) {
      state.graph.nodes[newId].x = prevNode.x + 240;
      state.graph.nodes[newId].y = prevNode.y;
    }
    addEdge(prevId, newId, '');
  }

  function buildButtons() {
    NODE_TYPES.forEach(node => {
      const btn = document.createElement('button');
      btn.textContent = node.title;
      setHelp(btn, node.help);
      btn.addEventListener('click', () => {
        const prevId = selectedId;
        const id = addNode(node.type);
        maybeAutoConnect(prevId, id);
        setSelectedId(id);
        renderAll();
      });
      nodeButtons.appendChild(btn);
    });
  }

  function buildTemplates() {
    templateList.innerHTML = '';
    TEMPLATES.forEach(template => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'template-item';
      btn.innerHTML = `<strong>${template.name}</strong><span>${template.description}</span>`;
      setHelp(btn, TEMPLATE_HELP[template.id] || template.description);
      btn.addEventListener('click', () => {
        if (!confirm(`Load template "${template.name}"? This will replace the current workflow.`)) {
          return;
        }
        const built = buildTemplateGraph(template.id);
        if (!built) return;
        replaceState({ id: null, name: built.name, graph: { nodes: built.nodes, edges: built.edges } });
        setSelectedId(null);
        setStatus('Template loaded');
        renderAll();
      });
      templateList.appendChild(btn);
    });
  }

  function initQuickActions() {
    if (!quickActions) return;
    const helpMap = {
      email: 'What: Build a simple email workflow.\nHow: Creates Start -> Email with sample fields.\nWhy: Send quick messages without setup.',
      'search-summary': 'What: Search the web, summarize, then email.\nHow: Creates Search -> LLM -> Email.\nWhy: Quick research reports.',
      'schedule-email': 'What: Send a recurring scheduled email.\nHow: Creates Loop -> Schedule -> Email.\nWhy: Automate reminders.',
      'run-script': 'What: Run a Python script.\nHow: Creates Start -> Python Script.\nWhy: Execute custom code fast.'
    };
    quickActions.querySelectorAll('button[data-quick]').forEach((btn) => {
      const key = btn.dataset.quick;
      if (helpMap[key]) {
        setHelp(btn, helpMap[key]);
      }
    });
    quickActions.addEventListener('click', (event) => {
      const btn = event.target.closest('button[data-quick]');
      if (!btn) return;
      const type = btn.dataset.quick;
      buildQuickFlow(type);
    });
  }

  function initMethodButtons() {
    if (!methodButtons) return;
    const methodHelp = {
      nodeButtons: 'What: Visual canvas builder.\nHow: Click node buttons and connect them.\nWhy: Most flexible way to build automations.',
      pipelineSummary: 'What: Linear pipeline builder.\nHow: Add scripts in order and apply to canvas.\nWhy: Fast list-based setup.',
      templateList: 'What: Template gallery.\nHow: Load a prebuilt workflow.\nWhy: Start from proven examples.',
      scriptList: 'What: Script library.\nHow: Pick a script and add it as a node.\nWhy: Reuse custom code.'
    };
    methodButtons.querySelectorAll('[data-scroll]').forEach((btn) => {
      const key = btn.dataset.scroll;
      if (methodHelp[key]) {
        setHelp(btn, methodHelp[key]);
      }
    });
    const symblicLink = methodButtons.querySelector('.method-link');
    if (symblicLink) {
      setHelp(symblicLink, 'What: Text mode builder (Symblic).\nHow: Write one instruction per line and compile.\nWhy: Fast, deterministic automation setup.');
    }
    methodButtons.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-scroll]');
      if (!btn) return;
      const targetId = btn.dataset.scroll;
      const target = document.getElementById(targetId);
      if (target && target.scrollIntoView) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  function buildQuickFlow(type) {
    const hasExisting = Object.keys(state.graph.nodes || {}).length > 0;
    if (hasExisting) {
      const ok = confirm('Replace the current workflow with this starter? This will clear the canvas.');
      if (!ok) return;
    }
    const nameMap = {
      email: 'Quick Email',
      'search-summary': 'Quick Search Summary',
      'schedule-email': 'Quick Scheduled Email',
      'run-script': 'Quick Script Runner'
    };
    const nextName = nameMap[type] || 'Quick Starter';
    replaceState({ id: null, name: nextName, graph: { nodes: {}, edges: [] } });
    if (workflowSelect) workflowSelect.value = '';
    const baseX = 120;
    const baseY = 140;
    const spacing = 240;
    const startId = addNode('start', { title: 'Start' });
    state.graph.nodes[startId].x = baseX;
    state.graph.nodes[startId].y = baseY;
    let lastId = startId;
    let stepIndex = 0;

    const addStep = (nodeType, title, data) => {
      stepIndex += 1;
      const id = addNode(nodeType, { title, data });
      state.graph.nodes[id].x = baseX + spacing * stepIndex;
      state.graph.nodes[id].y = baseY;
      addEdge(lastId, id, '');
      lastId = id;
      return id;
    };

    if (type === 'email') {
      addStep('email', 'Send Email', {
        to: '',
        subject: 'Hello from Automation Studio',
        body: 'Hi there,\n\nThis is a friendly automated email.\n\nThanks!'
      });
      setStatus('Starter: email flow');
      if (quickActionStatus) quickActionStatus.textContent = 'Built a simple Start -> Email workflow.';
    } else if (type === 'search-summary') {
      addStep('websearch', 'Search the Web', {
        query: 'type your topic here',
        maxResults: 5
      });
      addStep('ollama', 'Summarize Results', {
        provider: 'ollama',
        model: 'llama3.1',
        prompt: 'Summarize these search results in 5 bullet points:\n{{last_output}}',
        contextMode: 'clear',
        outputMode: 'app',
        emailSubject: 'Search summary'
      });
      addStep('email', 'Send Summary Email', {
        to: '',
        subject: 'Search summary',
        body: '{{last_output}}'
      });
      setStatus('Starter: search + summarize');
      if (quickActionStatus) quickActionStatus.textContent = 'Built a Search -> Summarize -> Email workflow.';
    } else if (type === 'schedule-email') {
      addStep('loop', 'Repeat', { count: 0, delaySeconds: 0 });
      addStep('schedule', 'Schedule', {
        recurrence: 'daily at 09:00',
        scheduleMode: 'once'
      });
      addStep('email', 'Send Scheduled Email', {
        to: '',
        subject: 'Scheduled hello',
        body: 'Hello!\n\nThis is your scheduled email.'
      });
      setStatus('Starter: scheduled email');
      if (quickActionStatus) quickActionStatus.textContent = 'Built a Loop -> Schedule -> Email workflow.';
    } else if (type === 'run-script') {
      addStep('python_script', 'Run Script', {
        scriptPath: '',
        functionName: '',
        params: {},
        inputParam: ''
      });
      setStatus('Starter: script runner');
      if (quickActionStatus) quickActionStatus.textContent = 'Built a Start -> Python Script workflow.';
    } else {
      if (quickActionStatus) quickActionStatus.textContent = 'Unknown starter type.';
    }

    setSelectedId(lastId);
    renderAll();
  }

  function refreshWorkflows(selectedIdOverride) {
    apiGet('/api/automation/list').then(data => {
      workflowSelect.innerHTML = '';
      const items = data.items || [];
      const emptyOption = document.createElement('option');
      emptyOption.value = '';
      emptyOption.textContent = 'Select workflow';
      workflowSelect.appendChild(emptyOption);
      items.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = item.name || item.id;
        workflowSelect.appendChild(opt);
      });
      if (selectedIdOverride) {
        workflowSelect.value = selectedIdOverride;
      } else if (state.id) {
        workflowSelect.value = state.id;
      }
    });
  }

  function saveWorkflow() {
    const name = prompt('Workflow name', state.name || 'Automation');
    if (!name) return;
    state.name = name;
    apiPost('/api/automation/save', {
      id: state.id,
      name: state.name,
      graph: state.graph
    }).then(resp => {
      if (resp.item) {
        state.id = resp.item.id;
        setStatus('Saved');
        refreshWorkflows(state.id);
      } else {
        alert(resp.error || 'Save failed');
      }
    });
  }

  function loadWorkflow(id) {
    apiGet('/api/automation/list').then(data => {
      const found = (data.items || []).find(item => item.id === id);
      if (found) {
        replaceState({ id: found.id, name: found.name, graph: found.graph || { nodes: {}, edges: [] } });
        setStatus('Loaded');
        renderAll();
      }
    });
  }

  function updateApiStatus(text) {
    apiStatus.textContent = text;
  }

  function checkApi() {
    const base = getApiBase();
    if (!base) {
      updateApiStatus('Default server');
      return;
    }
    apiGet('/api/automation/health').then(resp => {
      if (resp && resp.ok) {
        updateApiStatus(`Connected (v${resp.version || '1'})`);
      } else {
        updateApiStatus('Connected');
      }
    }).catch(() => {
      updateApiStatus('Unavailable');
    });
  }

  initGraph({
    nodesElement: nodesEl,
    linksElement: linksEl,
    onNodeSelect: (id) => {
      setSelectedId(id);
      renderAll();
    },
    onEdgeConnect: ({ mode, from, to }) => {
      if (mode === 'from') {
        setStatus(`Connect from ${from}`);
      } else if (mode === 'to') {
        const label = prompt('Edge label (optional)', '') || '';
        addEdge(from, to, label);
        setStatus('Unsaved');
        renderAll();
      }
    }
  });

  workflowSelect.addEventListener('change', (e) => {
    if (e.target.value) {
      loadWorkflow(e.target.value);
    }
  });

  saveBtn.addEventListener('click', saveWorkflow);
  newBtn.addEventListener('click', () => {
    replaceState({ id: null, name: 'New Automation', graph: { nodes: {}, edges: [] } });
    setStatus('New workflow');
    renderAll();
  });

  connectBtn.addEventListener('click', () => {
    const enabled = !connectBtn.classList.contains('success');
    connectBtn.classList.toggle('success', enabled);
    connectBtn.textContent = enabled ? 'Connecting...' : 'Connect Nodes';
    setConnectMode(enabled);
  });

  deleteBtn.addEventListener('click', () => {
    if (!selectedId) return;
    if (confirm('Delete selected node?')) {
      removeNode(selectedId);
      setSelectedId(null);
      renderAll();
    }
  });

  apiBaseInput.value = getApiBase() || '';
  apiBaseSave.addEventListener('click', () => {
    setApiBase(apiBaseInput.value.trim());
    checkApi();
  });

  applyHelpText();
  buildButtons();
  initQuickActions();
  initMethodButtons();
  buildTemplates();
  refreshWorkflows();
  renderAll();
  checkApi();
  maybeLoadSymblicWorkflow();

  const scriptLibrary = initScriptLibrary({
    listEl: scriptList,
    detailsEl: scriptDetails,
    searchInput: scriptSearch,
    categorySelect: scriptCategory,
    viewSelect: scriptView,
    addBtn: scriptAddNode,
    openBtn: scriptOpenCode,
    editBtn: scriptEdit,
    reloadBtn: scriptReload,
    scriptsDirInput,
    scriptsDirApply,
    editorModal: scriptEditor,
    editorTextarea: scriptEditorText,
    editorSave: scriptEditorSave,
    editorReload: scriptEditorReload,
    editorClose: scriptEditorClose,
    editorStatus: scriptEditorStatus,
    onAddScriptNode: (item, defaults) => {
      const title = item.name.replace(/\\.py$/i, '');
      const firstParam = item.params && item.params.length ? item.params[0].name : '';
      const data = {
        scriptPath: item.path,
        functionName: item.functionName || '',
        params: defaults || {},
        inputParam: firstParam || ''
      };
      const prevId = selectedId;
      const id = addNode('python_script', { title, data });
      maybeAutoConnect(prevId, id);
      setSelectedId(id);
      renderAll();
    }
  });

  const pipelineSyncState = { enabled: true, lock: false };

  if (pipelineSync) {
    pipelineSyncState.enabled = pipelineSync.checked;
    pipelineSync.addEventListener('change', () => {
      pipelineSyncState.enabled = pipelineSync.checked;
      if (pipelineStatus) {
        pipelineStatus.textContent = pipelineSyncState.enabled ? 'Sync enabled.' : 'Sync disabled.';
      }
      if (pipelineSyncState.enabled) syncPipelineFromGraph();
    });
  }

  function applyPipelineToCanvas(steps, options = {}) {
    if (!steps || !steps.length) return;
    if (options.replace) {
      replaceState({ id: null, name: state.name || 'New Automation', graph: { nodes: {}, edges: [] } });
    }
    const baseX = 120 + Object.keys(state.graph.nodes).length * 40;
    const baseY = 120;
    const startId = addNode('start', { title: 'Start' });
    state.graph.nodes[startId].x = baseX;
    state.graph.nodes[startId].y = baseY;
    let prevId = startId;
    steps.forEach((step, index) => {
      const data = {
        scriptPath: step.scriptPath,
        functionName: step.functionName,
        inputVar: step.inputVar,
        inputParam: step.inputParam,
        outputVar: step.outputVar,
        params: step.params || {}
      };
      const nodeId = addNode('python_script', { title: step.title, data });
      state.graph.nodes[nodeId].x = baseX + (index + 1) * 220;
      state.graph.nodes[nodeId].y = baseY;
      addEdge(prevId, nodeId, '');
      prevId = nodeId;
    });
    setSelectedId(prevId);
    if (!options.silent) {
      setStatus('Pipeline applied');
    }
    renderAll();
  }

  pipelineBuilder = initPipelineBuilder({
    listEl: pipelineList,
    detailsEl: pipelineDetails,
    addBtn: pipelineAddStep,
    removeBtn: pipelineRemoveStep,
    clearBtn: pipelineClear,
    applyBtn: pipelineApply,
    exportBtn: pipelineExport,
    importBtn: pipelineImport,
    importInput: pipelineImportFile,
    replaceToggle: pipelineReplace,
    statusEl: pipelineStatus,
    getSelectedScript: () => scriptLibrary.getSelected(),
    onApplyGraph: (steps, options) => {
      applyPipelineToCanvas(steps, { replace: options && options.replace });
    },
    onStepsChange: (steps) => {
      if (!pipelineSyncState.enabled || pipelineSyncState.lock) return;
      pipelineSyncState.lock = true;
      const shouldReplace = pipelineReplace ? pipelineReplace.checked : true;
      applyPipelineToCanvas(steps, { replace: shouldReplace, silent: true });
      pipelineSyncState.lock = false;
    }
  });

  syncPipelineFromGraph();

  if (scriptList && pipelineAddStep) {
    const updatePipelineAdd = () => {
      pipelineAddStep.disabled = !scriptLibrary.getSelected();
    };
    scriptList.addEventListener('click', updatePipelineAdd);
    updatePipelineAdd();
  }

  function syncPipelineFromGraph() {
    if (!pipelineBuilder || !pipelineSyncState.enabled || pipelineSyncState.lock) return;
    const result = derivePipelineSteps(state.graph);
    if (result.ok) {
      pipelineSyncState.lock = true;
      pipelineBuilder.setSteps(result.steps, { silent: true });
      if (pipelineStatus) {
        pipelineStatus.textContent = 'Synced from canvas.';
      }
      pipelineSyncState.lock = false;
    } else if (pipelineStatus) {
      pipelineStatus.textContent = result.reason || 'Sync paused.';
    }
  }

  function maybeLoadSymblicWorkflow() {
    const raw = localStorage.getItem('symblicWorkflow');
    if (!raw) return;
    localStorage.removeItem('symblicWorkflow');
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object' || !parsed.graph) {
        throw new Error('Invalid Symblic workflow payload.');
      }
      const name = parsed.name || 'Symblic Workflow';
      const shouldLoad = confirm(`Load Symblic workflow \"${name}\"? This will replace the current canvas.`);
      if (!shouldLoad) return;
      replaceState({ id: null, name, graph: parsed.graph });
      setSelectedId(null);
      setStatus('Symblic workflow loaded');
      renderAll();
    } catch (err) {
      alert(err.message || 'Failed to load Symblic workflow.');
    }
  }

  const history = initHistory({ container: runHistory, runLog, lastOutput });
  history.refresh();
  setInterval(() => history.refresh(), 10000);

  // ============================================================
  // CANVAS TOOLS IMPLEMENTATION
  // ============================================================

  function updateZoom(newZoom) {
    canvasState.zoom = Math.max(25, Math.min(200, newZoom));
    const scale = canvasState.zoom / 100;
    // Apply zoom to the inner elements of the canvas
    if (nodesContainer) {
      nodesContainer.style.transform = `scale(${scale})`;
      nodesContainer.style.transformOrigin = 'top left';
    }
    if (linksEl) {
      linksEl.style.transform = `scale(${scale})`;
      linksEl.style.transformOrigin = 'top left';
    }
    if (canvasZoom) canvasZoom.value = canvasState.zoom;
    if (canvasStatus) canvasStatus.textContent = `Zoom ${canvasState.zoom}%`;
  }

  function initCanvasTools() {
    // Load saved preferences
    const savedZoom = localStorage.getItem('canvasZoom');
    const savedTheme = localStorage.getItem('canvasTheme');
    const savedGrid = localStorage.getItem('canvasGrid');
    const savedSnap = localStorage.getItem('canvasSnap');
    const savedEasyMode = localStorage.getItem('canvasEasyMode');

    if (savedZoom) updateZoom(parseInt(savedZoom, 10));
    if (savedTheme && themeSelect) {
      themeSelect.value = savedTheme;
      document.body.dataset.theme = savedTheme;
    }
    if (savedGrid === 'false' && gridToggle) {
      gridToggle.checked = false;
      if (canvas) canvas.classList.add('grid-off');
    }
    if (savedSnap === 'true' && snapToggle) {
      snapToggle.checked = true;
      canvasState.snapToGrid = true;
    }
    if (savedEasyMode === 'true' && easyModeToggle) {
      easyModeToggle.checked = true;
      document.body.classList.add('easy-mode');
    }

    // Zoom slider
    if (canvasZoom) {
      canvasZoom.addEventListener('input', () => {
        updateZoom(parseInt(canvasZoom.value, 10));
        localStorage.setItem('canvasZoom', canvasState.zoom);
      });
    }

    // Zoom buttons
    if (zoomOut) {
      zoomOut.addEventListener('click', () => {
        updateZoom(canvasState.zoom - 10);
        localStorage.setItem('canvasZoom', canvasState.zoom);
      });
    }
    if (zoomIn) {
      zoomIn.addEventListener('click', () => {
        updateZoom(canvasState.zoom + 10);
        localStorage.setItem('canvasZoom', canvasState.zoom);
      });
    }
    if (zoomReset) {
      zoomReset.addEventListener('click', () => {
        updateZoom(100);
        localStorage.setItem('canvasZoom', 100);
      });
    }

    // Zoom to fit all nodes
    if (zoomFit) {
      zoomFit.addEventListener('click', () => {
        const nodes = Object.values(state.graph.nodes);
        if (!nodes.length) return;
        const minX = Math.min(...nodes.map(n => n.x));
        const maxX = Math.max(...nodes.map(n => n.x + 190));
        const minY = Math.min(...nodes.map(n => n.y));
        const maxY = Math.max(...nodes.map(n => n.y + 80));
        const width = maxX - minX + 100;
        const height = maxY - minY + 100;
        const canvasRect = canvas ? canvas.getBoundingClientRect() : { width: 800, height: 600 };
        const fitZoom = Math.min(
          (canvasRect.width / width) * 100,
          (canvasRect.height / height) * 100,
          150
        );
        updateZoom(Math.round(fitZoom));
        if (canvas) {
          canvas.scrollLeft = (minX - 50) * (canvasState.zoom / 100);
          canvas.scrollTop = (minY - 50) * (canvasState.zoom / 100);
        }
      });
    }

    // Center on selected node
    if (zoomSelection) {
      zoomSelection.addEventListener('click', () => {
        if (!selectedId) {
          if (canvasStatus) canvasStatus.textContent = 'No node selected';
          return;
        }
        const node = state.graph.nodes[selectedId];
        if (!node || !canvas) return;
        const canvasRect = canvas.getBoundingClientRect();
        const scale = canvasState.zoom / 100;
        canvas.scrollLeft = (node.x + 95) * scale - canvasRect.width / 2;
        canvas.scrollTop = (node.y + 40) * scale - canvasRect.height / 2;
        if (canvasStatus) canvasStatus.textContent = `Centered on ${node.title || node.type}`;
      });
    }

    // Auto layout
    if (autoLayout) {
      autoLayout.addEventListener('click', () => {
        const nodes = Object.values(state.graph.nodes);
        if (!nodes.length) return;

        // Find start nodes (nodes with no incoming edges)
        const incomingCount = {};
        nodes.forEach(n => { incomingCount[n.id] = 0; });
        state.graph.edges.forEach(e => {
          if (incomingCount[e.to] !== undefined) incomingCount[e.to]++;
        });

        const startNodes = nodes.filter(n => incomingCount[n.id] === 0);
        const visited = new Set();
        const levels = {};

        // BFS to assign levels
        const queue = startNodes.map(n => ({ node: n, level: 0 }));
        if (!queue.length && nodes.length) {
          queue.push({ node: nodes[0], level: 0 });
        }

        while (queue.length) {
          const { node, level } = queue.shift();
          if (visited.has(node.id)) continue;
          visited.add(node.id);
          if (!levels[level]) levels[level] = [];
          levels[level].push(node);

          // Find connected nodes
          state.graph.edges
            .filter(e => e.from === node.id)
            .forEach(e => {
              const targetNode = state.graph.nodes[e.to];
              if (targetNode && !visited.has(e.to)) {
                queue.push({ node: targetNode, level: level + 1 });
              }
            });
        }

        // Position nodes by level
        const originX = 100;
        const originY = 100;
        const xSpacing = 240;
        const ySpacing = 120;

        Object.entries(levels).forEach(([levelStr, levelNodes]) => {
          const level = parseInt(levelStr, 10);
          levelNodes.forEach((node, index) => {
            node.x = originX + level * xSpacing;
            node.y = originY + index * ySpacing;
          });
        });

        renderAll();
        setStatus('Auto layout applied');
        if (canvasStatus) canvasStatus.textContent = 'Layout complete';
      });
    }

    // Grid toggle
    if (gridToggle) {
      gridToggle.addEventListener('change', () => {
        if (canvas) {
          canvas.classList.toggle('grid-off', !gridToggle.checked);
        }
        localStorage.setItem('canvasGrid', gridToggle.checked);
      });
    }

    // Snap to grid toggle
    if (snapToggle) {
      snapToggle.addEventListener('change', () => {
        canvasState.snapToGrid = snapToggle.checked;
        localStorage.setItem('canvasSnap', snapToggle.checked);
      });
    }

    // Easy mode toggle
    if (easyModeToggle) {
      easyModeToggle.addEventListener('change', () => {
        document.body.classList.toggle('easy-mode', easyModeToggle.checked);
        localStorage.setItem('canvasEasyMode', easyModeToggle.checked);
      });
    }

    // Theme select
    if (themeSelect) {
      themeSelect.addEventListener('change', () => {
        document.body.dataset.theme = themeSelect.value;
        localStorage.setItem('canvasTheme', themeSelect.value);
      });
    }
  }

  initCanvasTools();

  // ============================================================
  // NODE NAVIGATOR IMPLEMENTATION
  // ============================================================

  function renderNodeNavigator() {
    if (!nodeList) return;

    const nodes = Object.values(state.graph.nodes);
    const searchTerm = nodeSearch ? nodeSearch.value.toLowerCase() : '';

    // Filter nodes by search
    const filtered = nodes.filter(node => {
      if (!searchTerm) return true;
      const title = (node.title || '').toLowerCase();
      const type = (node.type || '').toLowerCase();
      return title.includes(searchTerm) || type.includes(searchTerm);
    });

    // Update count
    if (nodeCount) {
      nodeCount.textContent = `${filtered.length} of ${nodes.length} nodes`;
    }

    // Render list
    nodeList.innerHTML = '';
    if (!filtered.length) {
      nodeList.textContent = searchTerm ? 'No matching nodes.' : 'No nodes yet.';
      return;
    }

    filtered.forEach(node => {
      const item = document.createElement('div');
      item.className = 'node-nav-item' + (node.id === selectedId ? ' active' : '');

      const info = document.createElement('div');
      info.className = 'node-nav-info';

      const title = document.createElement('div');
      title.className = 'node-nav-title';
      title.textContent = node.title || node.type;

      const meta = document.createElement('div');
      meta.className = 'node-nav-meta';
      const badge = document.createElement('span');
      badge.className = 'node-type-badge';
      badge.textContent = node.type;
      meta.appendChild(badge);

      info.appendChild(title);
      info.appendChild(meta);

      const actions = document.createElement('div');
      actions.className = 'node-nav-actions';

      const selectBtn = document.createElement('button');
      selectBtn.className = 'small primary';
      selectBtn.textContent = 'Select';
      selectBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        setSelectedId(node.id);
        renderAll();
        // Center the canvas on this node
        if (canvas) {
          const scale = canvasState.zoom / 100;
          const canvasRect = canvas.getBoundingClientRect();
          canvas.scrollLeft = (node.x + 95) * scale - canvasRect.width / 2;
          canvas.scrollTop = (node.y + 40) * scale - canvasRect.height / 2;
        }
      });

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'small danger';
      deleteBtn.textContent = 'Del';
      deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (confirm(`Delete node "${node.title || node.type}"?`)) {
          removeNode(node.id);
          setSelectedId(null);
          renderAll();
        }
      });

      actions.appendChild(selectBtn);
      actions.appendChild(deleteBtn);

      item.appendChild(info);
      item.appendChild(actions);
      item.addEventListener('click', () => {
        setSelectedId(node.id);
        renderAll();
      });

      nodeList.appendChild(item);
    });
  }

  // Search input handler
  if (nodeSearch) {
    nodeSearch.addEventListener('input', renderNodeNavigator);
  }

  // Initial render of navigator
  renderNodeNavigator();

  // ============================================================
  // WORKFLOW TOOLS IMPLEMENTATION
  // ============================================================

  function initWorkflowTools() {
    // Update workflow name input when state changes
    const syncWorkflowName = () => {
      if (workflowName) workflowName.value = state.name || '';
    };
    syncWorkflowName();

    // Rename workflow
    if (renameWorkflow && workflowName) {
      renameWorkflow.addEventListener('click', () => {
        const newName = workflowName.value.trim();
        if (!newName) {
          if (workflowToolStatus) workflowToolStatus.textContent = 'Name cannot be empty.';
          return;
        }
        state.name = newName;
        setStatus('Renamed (unsaved)');
        if (workflowToolStatus) workflowToolStatus.textContent = `Renamed to "${newName}"`;
      });
    }

    // Duplicate workflow
    if (duplicateWorkflow) {
      duplicateWorkflow.addEventListener('click', () => {
        const newName = `${state.name} (copy)`;
        const graphCopy = JSON.parse(JSON.stringify(state.graph));
        replaceState({ id: null, name: newName, graph: graphCopy });
        setSelectedId(null);
        setStatus('Duplicated (unsaved)');
        syncWorkflowName();
        if (workflowToolStatus) workflowToolStatus.textContent = 'Workflow duplicated.';
        renderAll();
      });
    }

    // Export workflow JSON
    if (exportWorkflowJson) {
      exportWorkflowJson.addEventListener('click', () => {
        const data = {
          id: state.id,
          name: state.name,
          graph: state.graph
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${state.name || 'workflow'}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        if (workflowToolStatus) workflowToolStatus.textContent = 'Exported to file.';
      });
    }

    // Import workflow JSON
    if (importWorkflowJson && importWorkflowFile) {
      importWorkflowJson.addEventListener('click', () => {
        importWorkflowFile.click();
      });

      importWorkflowFile.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = () => {
          try {
            const data = JSON.parse(reader.result);
            if (!data.graph || typeof data.graph !== 'object') {
              throw new Error('Invalid workflow: missing graph object');
            }

            const shouldLoad = confirm(`Import workflow "${data.name || 'Unnamed'}"? This will replace the current workflow.`);
            if (!shouldLoad) return;

            replaceState({
              id: null,
              name: data.name || 'Imported Workflow',
              graph: {
                nodes: data.graph.nodes || {},
                edges: data.graph.edges || []
              }
            });
            setSelectedId(null);
            setStatus('Imported');
            syncWorkflowName();
            if (workflowToolStatus) workflowToolStatus.textContent = 'Workflow imported.';
            renderAll();
          } catch (err) {
            alert(`Import failed: ${err.message}`);
            if (workflowToolStatus) workflowToolStatus.textContent = 'Import failed.';
          }
        };
        reader.readAsText(file);
        importWorkflowFile.value = '';
      });
    }
  }

  initWorkflowTools();

  // ============================================================
  // COMMAND PALETTE IMPLEMENTATION
  // ============================================================

  const COMMANDS = [
    { id: 'new', label: 'New Workflow', category: 'File', action: () => {
      replaceState({ id: null, name: 'New Automation', graph: { nodes: {}, edges: [] } });
      setStatus('New workflow');
      renderAll();
    }},
    { id: 'save', label: 'Save Workflow', category: 'File', action: () => saveWorkflow() },
    { id: 'export', label: 'Export as JSON', category: 'File', action: () => exportWorkflowJson?.click() },
    { id: 'import', label: 'Import from JSON', category: 'File', action: () => importWorkflowJson?.click() },
    { id: 'duplicate', label: 'Duplicate Workflow', category: 'File', action: () => duplicateWorkflow?.click() },
    { id: 'run', label: 'Run Workflow', category: 'Run', action: () => document.getElementById('runWorkflow')?.click() },
    { id: 'test', label: 'Test Run (No LLM)', category: 'Run', action: () => document.getElementById('runWorkflowTest')?.click() },
    { id: 'stop', label: 'Stop Run', category: 'Run', action: () => document.getElementById('stopRun')?.click() },
    { id: 'zoom-in', label: 'Zoom In', category: 'View', action: () => updateZoom(canvasState.zoom + 10) },
    { id: 'zoom-out', label: 'Zoom Out', category: 'View', action: () => updateZoom(canvasState.zoom - 10) },
    { id: 'zoom-reset', label: 'Reset Zoom', category: 'View', action: () => updateZoom(100) },
    { id: 'zoom-fit', label: 'Fit to Screen', category: 'View', action: () => zoomFit?.click() },
    { id: 'layout', label: 'Auto Layout Nodes', category: 'View', action: () => autoLayout?.click() },
    { id: 'grid', label: 'Toggle Grid', category: 'View', action: () => {
      if (gridToggle) {
        gridToggle.checked = !gridToggle.checked;
        gridToggle.dispatchEvent(new Event('change'));
      }
    }},
    { id: 'easy-mode', label: 'Toggle Easy Mode', category: 'View', action: () => {
      if (easyModeToggle) {
        easyModeToggle.checked = !easyModeToggle.checked;
        easyModeToggle.dispatchEvent(new Event('change'));
      }
    }},
    { id: 'theme-playful', label: 'Theme: Playful', category: 'View', action: () => {
      if (themeSelect) {
        themeSelect.value = 'playful';
        themeSelect.dispatchEvent(new Event('change'));
      }
    }},
    { id: 'theme-midnight', label: 'Theme: Midnight', category: 'View', action: () => {
      if (themeSelect) {
        themeSelect.value = 'midnight';
        themeSelect.dispatchEvent(new Event('change'));
      }
    }},
    { id: 'connect', label: 'Toggle Connect Mode', category: 'Edit', action: () => connectBtn?.click() },
    { id: 'delete', label: 'Delete Selected Node', category: 'Edit', action: () => deleteBtn?.click() },
    { id: 'deselect', label: 'Deselect All', category: 'Edit', action: () => {
      setSelectedId(null);
      renderAll();
    }},
    // Add node commands
    ...NODE_TYPES.map(nt => ({
      id: `add-${nt.type}`,
      label: `Add ${nt.title} Node`,
      category: 'Nodes',
      action: () => {
        const prevId = selectedId;
        const id = addNode(nt.type);
        maybeAutoConnect(prevId, id);
        setSelectedId(id);
        renderAll();
      }
    }))
  ];

  function initCommandPalette() {
    if (!commandPalette || !paletteInput || !paletteList) return;

    let selectedIndex = 0;
    let filteredCommands = [...COMMANDS];

    function openPalette() {
      commandPalette.classList.add('open');
      commandPalette.setAttribute('aria-hidden', 'false');
      paletteInput.value = '';
      paletteInput.focus();
      selectedIndex = 0;
      filterCommands('');
    }

    function closePalette() {
      commandPalette.classList.remove('open');
      commandPalette.setAttribute('aria-hidden', 'true');
    }

    function filterCommands(query) {
      const q = query.toLowerCase();
      filteredCommands = COMMANDS.filter(cmd =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.category.toLowerCase().includes(q)
      );
      renderPaletteList();
    }

    function renderPaletteList() {
      paletteList.innerHTML = '';
      if (!filteredCommands.length) {
        paletteList.textContent = 'No matching commands.';
        return;
      }

      filteredCommands.forEach((cmd, index) => {
        const item = document.createElement('div');
        item.className = 'palette-item' + (index === selectedIndex ? ' active' : '');
        item.innerHTML = `<span>${cmd.label}</span> <span class="muted small">${cmd.category}</span>`;
        item.addEventListener('click', () => {
          cmd.action();
          closePalette();
        });
        item.addEventListener('mouseenter', () => {
          selectedIndex = index;
          renderPaletteList();
        });
        paletteList.appendChild(item);
      });
    }

    function executeSelected() {
      if (filteredCommands[selectedIndex]) {
        filteredCommands[selectedIndex].action();
        closePalette();
      }
    }

    // Event listeners
    paletteInput.addEventListener('input', () => {
      selectedIndex = 0;
      filterCommands(paletteInput.value);
    });

    paletteInput.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, filteredCommands.length - 1);
        renderPaletteList();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, 0);
        renderPaletteList();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        executeSelected();
      } else if (e.key === 'Escape') {
        closePalette();
      }
    });

    if (paletteClose) {
      paletteClose.addEventListener('click', closePalette);
    }

    commandPalette.addEventListener('click', (e) => {
      if (e.target === commandPalette) {
        closePalette();
      }
    });

    // Keyboard shortcut (Ctrl/Cmd + K)
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (commandPalette.classList.contains('open')) {
          closePalette();
        } else {
          openPalette();
        }
      }
      // Escape to close
      if (e.key === 'Escape' && commandPalette.classList.contains('open')) {
        closePalette();
      }
    });

    // Initial render
    filterCommands('');
  }

  initCommandPalette();

  return {
    runLog,
    lastOutput,
    setStatus,
    refreshWorkflows,
    setRunStatus: (text) => { runLog.textContent = text; },
    setRunModeStatus: (text) => {
      if (runModeStatus) runModeStatus.textContent = text;
    }
  };
}
