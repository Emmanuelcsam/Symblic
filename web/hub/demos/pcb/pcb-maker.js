function mountPCBMaker(container) {
  const cellSize = 5;
  const cols = 52;
  const rows = 36;
  const canvasWidth = cols * cellSize;
  const canvasHeight = rows * cellSize;

  const partColors = {
    resistor: '#ff6b6b',
    capacitor: '#4ecdc4',
    inductor: '#ffe66d',
    chip: '#6c5ce7',
    connector: '#a29bfe',
    crystal: '#fd79a8',
    header: '#00b894',
    'mounting hole': '#2d3436'
  };

  const partTypes = Object.keys(partColors);

  let selectedType = null;
  let selectedPart = null;
  let parts = [];
  let traces = [];
  let isTraceMode = false;
  let traceSource = null;
  let isDragging = false;
  let dragStart = null;

  const canvas = document.createElement('canvas');
  canvas.width = canvasWidth;
  canvas.height = canvasHeight;
  const ctx = canvas.getContext('2d');

  const wrapper = document.createElement('div');
  wrapper.style.display = 'flex';
  wrapper.style.gap = '10px';
  wrapper.style.background = '#1a1a2e';
  wrapper.style.padding = '10px';
  wrapper.style.fontFamily = 'sans-serif';
  wrapper.style.fontSize = '12px';

  const leftPanel = document.createElement('div');
  leftPanel.style.display = 'flex';
  leftPanel.style.flexDirection = 'column';
  leftPanel.style.gap = '8px';

  const palette = document.createElement('div');
  palette.style.display = 'flex';
  palette.style.flexWrap = 'wrap';
  palette.style.gap = '4px';
  palette.style.maxWidth = '160px';

  partTypes.forEach(type => {
    const btn = document.createElement('button');
    btn.textContent = type;
    btn.style.background = partColors[type];
    btn.style.border = 'none';
    btn.style.padding = '6px 8px';
    btn.style.borderRadius = '3px';
    btn.style.cursor = 'pointer';
    btn.style.color = type === 'mounting hole' ? '#fff' : '#000';
    btn.onclick = () => { selectedType = type; };
    palette.appendChild(btn);
  });

  const rotateBtn = document.createElement('button');
  rotateBtn.textContent = 'Rotate';
  rotateBtn.style.background = '#636e72';
  rotateBtn.style.color = '#fff';
  rotateBtn.style.border = 'none';
  rotateBtn.style.padding = '6px 8px';
  rotateBtn.style.borderRadius = '3px';
  rotateBtn.style.cursor = 'pointer';
  rotateBtn.onclick = () => {
    if (selectedPart) {
      selectedPart.rotation = (selectedPart.rotation + 90) % 360;
      draw();
    }
  };

  const traceBtn = document.createElement('button');
  traceBtn.textContent = 'Trace';
  traceBtn.style.background = '#00b894';
  traceBtn.style.color = '#fff';
  traceBtn.style.border = 'none';
  traceBtn.style.padding = '6px 8px';
  traceBtn.style.borderRadius = '3px';
  traceBtn.style.cursor = 'pointer';
  traceBtn.onclick = () => {
    isTraceMode = true;
    traceSource = null;
    draw();
  };

  const exportBtn = document.createElement('button');
  exportBtn.textContent = 'Export';
  exportBtn.style.background = '#0984e3';
  exportBtn.style.color = '#fff';
  exportBtn.style.border = 'none';
  exportBtn.style.padding = '6px 8px';
  exportBtn.style.borderRadius = '3px';
  exportBtn.style.cursor = 'pointer';
  exportBtn.onclick = () => {
    const data = JSON.stringify({ parts, traces });
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'pcb-design.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const importInput = document.createElement('input');
  importInput.type = 'file';
  importInput.accept = '.json';
  importInput.style.display = 'none';
  importInput.onchange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const data = JSON.parse(ev.target.result);
          parts = data.parts || [];
          traces = data.traces || [];
          selectedPart = null;
          selectedType = null;
          isTraceMode = false;
          traceSource = null;
          draw();
        } catch (err) {}
      };
      reader.readAsText(file);
    }
    importInput.value = '';
  };

  const importBtn = document.createElement('button');
  importBtn.textContent = 'Import';
  importBtn.style.background = '#6c5ce7';
  importBtn.style.color = '#fff';
  importBtn.style.border = 'none';
  importBtn.style.padding = '6px 8px';
  importBtn.style.borderRadius = '3px';
  importBtn.style.cursor = 'pointer';
  importBtn.onclick = () => importInput.click();

  leftPanel.appendChild(palette);
  leftPanel.appendChild(rotateBtn);
  leftPanel.appendChild(traceBtn);
  leftPanel.appendChild(exportBtn);
  leftPanel.appendChild(importBtn);
  leftPanel.appendChild(importInput);

  const rightPanel = document.createElement('div');
  rightPanel.style.display = 'flex';
  rightPanel.style.flexDirection = 'column';
  rightPanel.style.gap = '8px';
  rightPanel.style.minWidth = '120px';

  const partsList = document.createElement('div');
  partsList.style.background = '#16213e';
  partsList.style.padding = '8px';
  partsList.style.borderRadius = '4px';
  partsList.style.color = '#fff';
  partsList.id = 'parts-list';
  rightPanel.appendChild(partsList);

  const canvasWrapper = document.createElement('div');
  canvasWrapper.style.flex = '1';
  canvasWrapper.appendChild(canvas);

  wrapper.appendChild(leftPanel);
  wrapper.appendChild(canvasWrapper);
  wrapper.appendChild(rightPanel);
  container.appendChild(wrapper);

  function updatePartsList() {
    const counts = {};
    parts.forEach(p => { counts[p.type] = (counts[p.type] || 0) + 1; });
    let html = '<b>Parts:</b><br>';
    partTypes.forEach(t => {
      if (counts[t]) html += `${t}: ${counts[t]}<br>`;
    });
    html += `<b>Traces:</b> ${traces.length}`;
    partsList.innerHTML = html;
  }

  function getCellFromPos(x, y) {
    const col = Math.floor(x / cellSize);
    const row = Math.floor(y / cellSize);
    return { col: Math.max(0, Math.min(cols - 1, col)), row: Math.max(0, Math.min(rows - 1, row)) };
  }

  function getPartAt(col, row) {
    return parts.find(p => p.col === col && p.row === row);
  }

  function drawGrid() {
    ctx.strokeStyle = '#0f3460';
    ctx.lineWidth = 0.3;
    for (let c = 0; c <= cols; c++) {
      ctx.beginPath();
      ctx.moveTo(c * cellSize, 0);
      ctx.lineTo(c * cellSize, canvasHeight);
      ctx.stroke();
    }
    for (let r = 0; r <= rows; r++) {
      ctx.beginPath();
      ctx.moveTo(0, r * cellSize);
      ctx.lineTo(canvasWidth, r * cellSize);
      ctx.stroke();
    }
  }

  function drawParts() {
    parts.forEach(p => {
      ctx.save();
      const centerX = (p.col + 0.5) * cellSize;
      const centerY = (p.row + 0.5) * cellSize;
      ctx.translate(centerX, centerY);
      ctx.rotate(p.rotation * Math.PI / 180);

      const isSelected = selectedPart === p;
      const color = isSelected ? '#ffffff' : partColors[p.type];

      if (p.type === 'mounting hole') {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(0, 0, cellSize * 0.3, 0, Math.PI * 2);
        ctx.fill();
      } else if (p.type === 'chip') {
        ctx.fillStyle = color;
        ctx.fillRect(-cellSize * 0.4, -cellSize * 0.3, cellSize * 0.8, cellSize * 0.6);
      } else if (p.type === 'connector' || p.type === 'header' || p.type === 'crystal') {
        ctx.fillStyle = color;
        ctx.fillRect(-cellSize * 0.3, -cellSize * 0.3, cellSize * 0.6, cellSize * 0.6);
      } else {
        ctx.fillStyle = color;
        ctx.fillRect(-cellSize * 0.4, -cellSize * 0.15, cellSize * 0.8, cellSize * 0.3);
      }

      if (isSelected) {
        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.rect(-cellSize * 0.55, -cellSize * 0.55, cellSize * 1.1, cellSize * 1.1);
        ctx.stroke();
      }
      ctx.restore();
    });
  }

  function drawTraces() {
    ctx.strokeStyle = '#ff9f43';
    ctx.lineWidth = 1.5;
    traces.forEach(t => {
      const p1 = parts.find(p => p.id === t.from);
      const p2 = parts.find(p => p.id === t.to);
      if (p1 && p2) {
        const x1 = (p1.col + 0.5) * cellSize;
        const y1 = (p1.row + 0.5) * cellSize;
        const x2 = (p2.col + 0.5) * cellSize;
        const y2 = (p2.row + 0.5) * cellSize;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    });
  }

  function draw() {
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, canvasWidth, canvasHeight);
    drawGrid();
    drawTraces();
    drawParts();
    updatePartsList();
  }

  function hitTest(x, y) {
    const col = Math.floor(x / cellSize);
    const row = Math.floor(y / cellSize);
    return parts.find(p => p.col === col && p.row === row);
  }

  canvas.onmousedown = (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (isTraceMode) {
      const part = hitTest(x, y);
      if (part) {
        if (!traceSource) {
          traceSource = part;
        } else if (traceSource !== part) {
          traces.push({ from: traceSource.id, to: part.id });
          traceSource = null;
        }
        draw();
      }
      return;
    }

    if (selectedType) {
      const cell = getCellFromPos(x, y);
      if (!getPartAt(cell.col, cell.row)) {
        const id = Date.now() + Math.random();
        parts.push({ id, type: selectedType, col: cell.col, row: cell.row, rotation: 0 });
        selectedPart = null;
        draw();
      }
    } else {
      const part = hitTest(x, y);
      if (part) {
        selectedPart = part;
        isDragging = true;
        dragStart = { x, y };
        draw();
      }
    }
  };

  canvas.onmousemove = (e) => {
    if (!isDragging || !selectedPart) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const dx = x - dragStart.x;
    const dy = y - dragStart.y;

    if (Math.abs(dx) >= cellSize || Math.abs(dy) >= cellSize) {
      const newCol = selectedPart.col + Math.round(dx / cellSize);
      const newRow = selectedPart.row + Math.round(dy / cellSize);
      const newCell = { col: Math.max(0, Math.min(cols - 1, newCol)), row: Math.max(0, Math.min(rows - 1, newRow)) };

      if (newCell.col !== selectedPart.col || newCell.row !== selectedPart.row) {
        if (!getPartAt(newCell.col, newCell.row)) {
          selectedPart.col = newCell.col;
          selectedPart.row = newCell.row;
          dragStart = { x, y };
          draw();
        }
      }
    }
  };

  canvas.onmouseup = () => { isDragging = false; };
  canvas.onmouseleave = () => { isDragging = false; };

  canvas.onkeydown = (e) => {
    if (e.key === 'Delete' && selectedPart) {
      parts = parts.filter(p => p !== selectedPart);
      selectedPart = null;
      draw();
    } else if (e.key === 'Escape') {
      if (isTraceMode) {
        isTraceMode = false;
        traceSource = null;
        draw();
      } else {
        selectedPart = null;
        selectedType = null;
        draw();
      }
    }
  };

  canvas.tabIndex = 0;
  canvas.style.outline = 'none';
  canvas.style.background = '#1a1a2e';

  draw();
}
