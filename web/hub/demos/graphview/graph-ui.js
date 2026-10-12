/**
 * graph-ui.js
 *
 * Settings panel UI for Obsidian-style beta-graphview.
 * Self-contained ECMAScript 2020. No imports or external dependencies.
 */

(function () {
  'use strict';

  /**
   * Mounts the graph settings panel into the given container.
   *
   * @param {HTMLElement|string} container - The DOM container or selector to mount into.
   * @param {Object} renderer - The GraphRenderer instance.
   * @param {Object} engine - The GraphEngine instance.
   * @param {Array} data - The vault data array of note items.
   * @returns {HTMLElement} The created settings panel element.
   */
  function mountGraphUI(container, renderer, engine, data) {
    const doc = typeof document !== 'undefined' ? document : null;
    if (!doc) {
      return null;
    }

    // Resolve container element
    let targetContainer = container;
    if (typeof container === 'string') {
      targetContainer = doc.querySelector(container);
    }

    // Create the settings panel element
    const panel = doc.createElement('div');
    panel.className = 'graph-settings-panel graph-settings';
    panel.setAttribute('title', 'Graph settings');
    panel.setAttribute('aria-label', 'Graph settings');
    panel.dataset.title = 'Graph settings';

    // Panel title heading
    const title = doc.createElement('h2');
    title.className = 'graph-settings-title';
    title.textContent = 'Graph settings';
    panel.appendChild(title);

    // Helper to safely get option from renderer
    function getRendererOption(optName, fallback) {
      if (renderer && typeof renderer.getOption === 'function') {
        const val = renderer.getOption(optName);
        if (val !== undefined) return val;
      }
      return fallback;
    }

    // Helper to safely set option on renderer
    function setRendererOption(optName, val) {
      if (renderer && typeof renderer.setOption === 'function') {
        renderer.setOption(optName, val);
      }
    }

    // Helper to safely get parameter from engine
    function getEngineParameter(paramName, fallback) {
      if (engine && typeof engine.getParameter === 'function') {
        const val = engine.getParameter(paramName);
        if (val !== undefined) return val;
      }
      return fallback;
    }

    // Helper to safely set parameter on engine
    function setEngineParameter(paramName, val) {
      if (engine && typeof engine.setParameter === 'function') {
        engine.setParameter(paramName, val);
      }
    }

    // Helper to create a toggle (checkbox) control
    function createToggle(labelText, optName, defaultVal) {
      const initialVal = Boolean(getRendererOption(optName, defaultVal));

      const row = doc.createElement('div');
      row.className = 'graph-control graph-control-toggle control-row';
      row.dataset.control = optName;
      row.dataset.option = optName;

      const label = doc.createElement('label');
      label.textContent = labelText;
      const inputId = 'control-' + optName;
      label.htmlFor = inputId;

      const input = doc.createElement('input');
      input.type = 'checkbox';
      input.id = inputId;
      input.name = optName;
      input.checked = initialVal;
      input.dataset.option = optName;

      const valSpan = doc.createElement('span');
      valSpan.className = 'control-value';
      valSpan.dataset.for = inputId;
      valSpan.textContent = String(input.checked);

      function update() {
        const checked = Boolean(input.checked);
        valSpan.textContent = String(checked);
        setRendererOption(optName, checked);
      }

      input.addEventListener('change', update);
      input.addEventListener('input', update);
      input.addEventListener('click', update);

      row.appendChild(label);
      row.appendChild(input);
      row.appendChild(valSpan);
      panel.appendChild(row);

      return { row, input, valSpan };
    }

    // Helper to create a slider (range) control
    function createSlider(labelText, name, isEngine, defaultVal, min, max, step, isInt) {
      const initialVal = isEngine
        ? getEngineParameter(name, defaultVal)
        : getRendererOption(name, defaultVal);

      const numVal = Number(initialVal !== undefined ? initialVal : defaultVal);

      const row = doc.createElement('div');
      row.className = 'graph-control graph-control-slider control-row';
      row.dataset.control = name;
      if (isEngine) {
        row.dataset.param = name;
      } else {
        row.dataset.option = name;
      }

      const label = doc.createElement('label');
      label.textContent = labelText;
      const inputId = 'control-' + name;
      label.htmlFor = inputId;

      const input = doc.createElement('input');
      input.type = 'range';
      input.id = inputId;
      input.name = name;
      input.min = String(min);
      input.max = String(max);
      input.step = String(step);
      input.value = String(numVal);
      if (isEngine) {
        input.dataset.param = name;
      } else {
        input.dataset.option = name;
      }

      const valSpan = doc.createElement('span');
      valSpan.className = 'control-value';
      valSpan.dataset.for = inputId;
      valSpan.textContent = String(input.value);

      function update() {
        const rawVal = isInt ? parseInt(input.value, 10) : parseFloat(input.value);
        valSpan.textContent = String(input.value);
        if (isEngine) {
          setEngineParameter(name, rawVal);
          if (engine && typeof engine.reheat === 'function') {
            engine.reheat();
          }
        } else {
          setRendererOption(name, rawVal);
        }
      }

      input.addEventListener('input', update);
      input.addEventListener('change', update);

      row.appendChild(label);
      row.appendChild(input);
      row.appendChild(valSpan);
      panel.appendChild(row);

      return { row, input, valSpan };
    }

    // 1. Animation toggle bound to renderer option animate
    createToggle('Animation', 'animate', true);

    // 2. Arrows toggle bound to renderer option arrows
    createToggle('Arrows', 'arrows', false);

    // 3. Labels toggle bound to renderer option labels
    createToggle('Labels', 'labels', true);

    // 4. Node size slider bound to renderer option nodeSize
    createSlider('Node size', 'nodeSize', false, 1.0, 0.1, 10, 0.1, false);

    // 5. Text fade threshold slider bound to renderer option textFadeThreshold
    createSlider('Text fade threshold', 'textFadeThreshold', false, 200, 0, 1000, 1, false);

    // 6. Focus depth slider bound to renderer option focusDepth
    createSlider('Focus depth', 'focusDepth', false, 0, 0, 10, 1, true);

    // 7. Center force slider bound to engine parameter centerStrength
    createSlider('Center force', 'centerStrength', true, 0.05, 0, 1, 0.005, false);

    // 8. Link force slider bound to engine parameter linkStrength
    createSlider('Link force', 'linkStrength', true, 0.1, 0, 1, 0.01, false);

    // 9. Link distance slider bound to engine parameter linkDistance
    createSlider('Link distance', 'linkDistance', true, 30, 1, 300, 1, false);

    // 10. Repel force slider bound to engine parameter repelStrength
    createSlider('Repel force', 'repelStrength', true, 50, 0, 300, 1, false);

    // 11. Collision slider bound to engine parameter collideStrength
    createSlider('Collision', 'collideStrength', true, 0.5, 0, 2, 0.05, false);

    // 12. Search field
    // Reads initial value with getOption if available
    const initialHighlight = getRendererOption('highlight', null);

    const searchRow = doc.createElement('div');
    searchRow.className = 'graph-control graph-control-search control-row';
    searchRow.dataset.control = 'search';

    const searchLabel = doc.createElement('label');
    searchLabel.textContent = 'Search';
    const searchInputId = 'control-search';
    searchLabel.htmlFor = searchInputId;

    const searchInput = doc.createElement('input');
    searchInput.type = 'text';
    searchInput.id = searchInputId;
    searchInput.name = 'search';
    searchInput.placeholder = 'Search notes and tags...';
    searchInput.setAttribute('aria-label', 'Search');
    searchInput.value = typeof initialHighlight === 'string' ? initialHighlight : '';

    const searchValSpan = doc.createElement('span');
    searchValSpan.className = 'control-value';
    searchValSpan.dataset.for = searchInputId;
    searchValSpan.textContent = searchInput.value;
    searchValSpan.dataset.value = searchInput.value || 'none';

    function performSearch() {
      const query = searchInput.value;
      searchValSpan.textContent = query;
      searchValSpan.dataset.value = query || 'none';

      if (!query || !query.trim()) {
        setRendererOption('highlight', null);
        return;
      }

      const q = query.trim().toLowerCase();
      const qTag = q.startsWith('#') ? q.slice(1) : q;
      const matched = [];
      const seen = new Set();

      const vaultData = Array.isArray(data)
        ? data
        : (typeof VAULT_DATA !== 'undefined' && Array.isArray(VAULT_DATA) ? VAULT_DATA : []);

      for (let i = 0; i < vaultData.length; i++) {
        const item = vaultData[i];
        if (!item || !item.id) continue;

        // Check note name
        let nameMatch = false;
        if (typeof item.name === 'string') {
          nameMatch = item.name.toLowerCase().includes(q);
        } else if (typeof item.id === 'string') {
          nameMatch = item.id.toLowerCase().includes(q);
        }

        // Check tags
        let tagMatch = false;
        if (Array.isArray(item.tags)) {
          for (let j = 0; j < item.tags.length; j++) {
            const tag = item.tags[j];
            if (typeof tag === 'string') {
              const tLower = tag.toLowerCase();
              if (tLower.includes(q) || (qTag && tLower.includes(qTag))) {
                tagMatch = true;
                break;
              }
            }
          }
        }

        if ((nameMatch || tagMatch) && !seen.has(item.id)) {
          seen.add(item.id);
          matched.push(item.id);
        }
      }

      setRendererOption('highlight', matched);
    }

    searchInput.addEventListener('input', performSearch);
    searchInput.addEventListener('change', performSearch);
    searchInput.addEventListener('keyup', performSearch);

    searchRow.appendChild(searchLabel);
    searchRow.appendChild(searchInput);
    searchRow.appendChild(searchValSpan);
    panel.appendChild(searchRow);

    // 13. Attachments filter toggle bound to renderer filter switch attachments
    createToggle('Attachments', 'attachments', true);

    // 14. Unresolved filter toggle bound to renderer filter switch unresolved
    createToggle('Unresolved', 'unresolved', true);

    // 15. Orphans filter toggle bound to renderer filter switch orphans
    createToggle('Orphans', 'orphans', true);

    // 16. Tags filter toggle bound to renderer filter switch tags
    createToggle('Tags', 'tags', true);

    // Insert panel into container
    if (targetContainer && typeof targetContainer.appendChild === 'function') {
      targetContainer.appendChild(panel);
    }

    return panel;
  }

  // Global export
  if (typeof globalThis !== 'undefined') {
    globalThis.mountGraphUI = mountGraphUI;
  }
  if (typeof window !== 'undefined') {
    window.mountGraphUI = mountGraphUI;
  }
})();
