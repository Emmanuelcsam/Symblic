'use strict';

function mountPCBInfo(container, core, parts, renderer, onSelect) {
  // Build category color map: first color found per category
  const categoryColors = {};
  const allComponents = [];
  
  const collect = (list) => {
    if (!list || !list.length) return;
    for (const c of list) {
      if (!c.id) continue;
      allComponents.push(c);
      const cat = c.category || '';
      if (cat && !categoryColors[cat] && c.color) {
        categoryColors[cat] = c.color;
      }
    }
  };
  
  collect(core.components);
  collect(parts.components);
  
  // Sort by id for consistent ordering
  allComponents.sort((a, b) => String(a.id).localeCompare(String(b.id)));
  
  // Compute category counts
  const categoryCounts = {};
  for (const c of allComponents) {
    const cat = c.category || 'uncategorized';
    categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
  }
  
  // State
  let selectedComponent = null;
  let walkthroughIndex = 0;
  let searchQuery = '';
  
  // Build DOM
  const panel = document.createElement('div');
  panel.style.fontFamily = 'sans-serif';
  panel.style.fontSize = '13px';
  panel.style.background = '#1a1a2e';
  panel.style.color = '#e0e0e0';
  panel.style.padding = '10px';
  panel.style.borderRadius = '6px';
  panel.style.display = 'flex';
  panel.style.flexDirection = 'column';
  panel.style.gap = '8px';
  panel.style.height = '100%';
  panel.style.overflow = 'hidden';
  
  // Stats line
  const statsLine = document.createElement('div');
  statsLine.style.fontSize = '11px';
  statsLine.style.color = '#a0a0c0';
  statsLine.style.padding = '4px 6px';
  statsLine.style.background = '#111';
  statsLine.style.borderRadius = '4px';
  
  const total = allComponents.length;
  const statParts = ['Total: ' + total];
  for (const cat of Object.keys(categoryCounts).sort()) {
    statParts.push(cat + '=' + categoryCounts[cat]);
  }
  statsLine.textContent = statParts.join(' ');
  
  // Legend
  const legend = document.createElement('div');
  legend.style.display = 'flex';
  legend.style.flexWrap = 'wrap';
  legend.style.gap = '8px';
  legend.style.padding = '4px';
  
  for (const cat of Object.keys(categoryColors).sort()) {
    const swatch = document.createElement('span');
    swatch.style.display = 'inline-flex';
    swatch.style.alignItems = 'center';
    swatch.style.gap = '4px';
    swatch.style.fontSize = '11px';
    const colorBox = document.createElement('span');
    colorBox.style.width = '12px';
    colorBox.style.height = '12px';
    colorBox.style.borderRadius = '2px';
    colorBox.style.background = categoryColors[cat];
    colorBox.style.border = '1px solid #444';
    colorBox.style.display = 'inline-block';
    colorBox.style.verticalAlign = 'middle';
    swatch.appendChild(colorBox);
    const label = document.createElement('span');
    label.textContent = cat + ' (' + (categoryCounts[cat] || 0) + ') ';
    swatch.appendChild(label);
    legend.appendChild(swatch);
  }
  
  // Search field
  const searchRow = document.createElement('div');
  searchRow.style.display = 'flex';
  searchRow.style.gap = '6px';
  
  const searchInput = document.createElement('input');
  searchInput.type = 'text';
  searchInput.placeholder = 'Search by name or category...';
  searchInput.style.flex = '1';
  searchInput.style.padding = '6px 8px';
  searchInput.style.borderRadius = '4px';
  searchInput.style.border = '1px solid #333';
  searchInput.style.background = '#252540';
  searchInput.style.color = '#e0e0e0';
  searchInput.style.fontSize = '13px';
  searchInput.addEventListener('input', () => {
    searchQuery = searchInput.value.toLowerCase();
    renderList();
  });
  
  searchRow.appendChild(searchInput);
  
  // Component list
  const listContainer = document.createElement('div');
  listContainer.style.flex = '1';
  listContainer.style.overflow = 'auto';
  listContainer.style.border = '1px solid #333';
  listContainer.style.borderRadius = '4px';
  listContainer.style.background = '#181828';
  
  const componentList = document.createElement('div');
  componentList.style.padding = '4px';
  listContainer.appendChild(componentList);
  
  // Detail card
  const detailCard = document.createElement('div');
  detailCard.style.padding = '8px';
  detailCard.style.border = '1px solid #333';
  detailCard.style.borderRadius = '4px';
  detailCard.style.background = '#181828';
  detailCard.style.fontSize = '12px';
  detailCard.style.minHeight = '100px';
  
  // Walkthrough button
  const walkthroughRow = document.createElement('div');
  const walkthroughButton = document.createElement('button');
  walkthroughButton.textContent = 'Walkthrough';
  walkthroughButton.style.padding = '8px 16px';
  walkthroughButton.style.borderRadius = '4px';
  walkthroughButton.style.border = '1px solid #333';
  walkthroughButton.style.background = '#0a3d62';
  walkthroughButton.style.color = '#fff';
  walkthroughButton.style.cursor = 'pointer';
  walkthroughButton.style.fontSize = '13px';
  walkthroughButton.addEventListener('click', () => {
    if (allComponents.length === 0) return;
    // Advance walkthrough
    walkthroughIndex = walkthroughIndex % allComponents.length;
    selectComponent(allComponents[walkthroughIndex]);
    walkthroughIndex = (walkthroughIndex + 1) % allComponents.length;
  });
  walkthroughRow.appendChild(walkthroughButton);
  
  // Assemble panel
  panel.appendChild(statsLine);
  panel.appendChild(legend);
  panel.appendChild(searchRow);
  panel.appendChild(listContainer);
  panel.appendChild(detailCard);
  panel.appendChild(walkthroughRow);
  
  container.appendChild(panel);
  
  // Helper: format position/size
  const fmt = (v) => {
    if (v === undefined || v === null) return '?';
    return v.toFixed(v % 1 === 0 ? 0 : 2);
  };
  
  const formatPos = (p) => {
    if (!p) return '?';
    return '(' + fmt(p.x) + ', ' + fmt(p.y) + ', ' + fmt(p.z) + ') mm';
  };
  
  const formatSize = (s) => {
    if (!s) return '?';
    return fmt(s.w) + ' x ' + fmt(s.d) + ' x ' + fmt(s.h) + ' mm';
  };
  
  // Select a component
  const selectComponent = (comp) => {
    selectedComponent = comp;
    if (renderer && renderer.focusComponent) {
      renderer.focusComponent(comp.id);
    }
    if (onSelect) {
      onSelect(comp.id);
    }
    renderDetail();
    renderList();
  };
  
  // Render detail card
  const renderDetail = () => {
    if (!selectedComponent) {
      detailCard.innerHTML = '<em style="color:#666">Select a component or use Walkthrough</em>';
      return;
    }
    const c = selectedComponent;
    const catColor = categoryColors[c.category] || c.color || '#888';
    detailCard.innerHTML = '<strong style="color:' + catColor + '">' + (c.name || c.id) + '</strong><br>' +
      '<em style="color:#a0a0c0">' + (c.category || '?') + '</em> | <em style="color:#a0a0c0">' + (c.package || '?') + '</em><br>' +
      'Position: ' + formatPos(c.position) + '<br>' +
      'Size: ' + formatSize(c.size) + '<br>' +
      'Pins: ' + (c.pins !== undefined ? c.pins : '?') + '<br>' +
      '<div style="margin-top:6px;font-size:11px;line-height:1.4;color:#ccc">' + (c.description || 'No description') + '</div>';
  };
  
  // Filter and render list
  const renderList = () => {
    const query = searchQuery.toLowerCase();
    const filtered = allComponents.filter(c => {
      if (!query) return true;
      const id = (c.id || '').toLowerCase();
      const name = (c.name || '').toLowerCase();
      const cat = (c.category || '').toLowerCase();
      return id.includes(query) || name.includes(query) || cat.includes(query);
    });
    
    componentList.innerHTML = '';
    const selectedId = selectedComponent ? selectedComponent.id : null;
    
    for (const c of filtered) {
      const item = document.createElement('div');
      item.style.padding = '6px 8px';
      item.style.borderRadius = '4px';
      item.style.cursor = 'pointer';
      item.style.display = 'flex';
      item.style.justifyContent = 'space-between';
      item.style.alignItems = 'center';
      
      const catColor = categoryColors[c.category] || c.color || '#888';
      const colorBox = document.createElement('span');
      colorBox.style.width = '10px';
      colorBox.style.height = '10px';
      colorBox.style.borderRadius = '2px';
      colorBox.style.background = catColor;
      colorBox.style.border = '1px solid #333';
      colorBox.style.marginRight = '6px';
      
      const label = document.createElement('span');
      label.textContent = c.id + ' ';
      
      const nameSpan = document.createElement('span');
      nameSpan.textContent = c.name || '';
      nameSpan.style.color = '#a0a0c0';
      nameSpan.style.fontSize = '11px';
      
      const left = document.createElement('span');
      left.style.display = 'flex';
      left.style.alignItems = 'center';
      left.appendChild(colorBox);
      left.appendChild(label);
      left.appendChild(nameSpan);
      
      const right = document.createElement('span');
      right.textContent = c.category || '';
      right.style.fontSize = '10px';
      right.style.color = '#6080a0';
      
      item.appendChild(left);
      item.appendChild(right);
      
      const isSelected = c.id === selectedId;
      item.style.background = isSelected ? '#36454f' : (c.color ? c.color + '18' : 'transparent');
      item.style.color = isSelected ? '#fff' : '#e0e0e0';
      
      item.addEventListener('click', () => selectComponent(c));
      item.addEventListener('mouseenter', () => {
        if (!isSelected) item.style.background = '#252540';
      });
      item.addEventListener('mouseleave', () => {
        if (!isSelected) item.style.background = c.color ? c.color + '18' : 'transparent';
      });
      
      componentList.appendChild(item);
    }
    
    if (filtered.length === 0) {
      const empty = document.createElement('div');
      empty.textContent = 'No components match the search';
      empty.style.padding = '8px';
      empty.style.color = '#666';
      empty.style.fontSize = '11px';
      componentList.appendChild(empty);
    }
  };
  
  // Initialize
  renderList();
  renderDetail();
}
