/* symblic-help: a "?" button, an explain mode (click any feature) and zero-to-mastery topics for the Symblic page.
   Content: symblic-help-content.json, generated from a read-only code inventory. No network beyond that file, no
   innerHTML: every node is built with createElement/textContent. */
(() => {
  'use strict';
  const CONTENT = 'symblic-help-content.json';
  let data = null, loading = null, explaining = false, outlined = null, panel = null, hint = null, opener = null, lastMove = 0;
  let opening = 0, pendingExplain = false, pendingPanel = false;
  const byId = new Map(), byLabel = new Map(), byTopic = new Map();

  function node(tag, props, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const kid of kids) if (kid) n.append(kid);
    return n;
  }
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const add = (map, key, topic) => { if (!key) return; if (!map.has(key)) map.set(key, []); map.get(key).push(topic); };

  function load() {
    if (data) return Promise.resolve(data);
    if (!loading) {
      loading = fetch(CONTENT, { cache: 'no-store', credentials: 'same-origin' })
        .then((r) => { if (!r.ok) throw new Error('help content ' + r.status); return r.json(); })
        .then((doc) => {
          for (const t of doc.topics) {
            byTopic.set(t.id, t);
            for (const id of t.ids) add(byId, id, t);
            for (const label of t.labels) add(byLabel, norm(label), t);
          }
          data = doc;
          return doc;
        })
        .catch((err) => { loading = null; throw err; });
    }
    return loading;
  }

  function tab() {
    const h = (location.hash || '').replace('#', '').split(/[/?&]/)[0];
    return data && data.tabs.includes(h) ? h : 'write';
  }
  function pick(list) {
    if (!list || !list.length) return null;
    const here = tab();
    return list.find((t) => t.tab === here) || list.find((t) => !t.tab) || list[0];
  }
  function overview() {
    const here = tab();
    return byTopic.get(here) || byTopic.get(here + '.tab') || byTopic.get('write');
  }
  // The element under a click or pointer, resolved at that moment: repaints replace the page's innerHTML.
  function resolve(target) {
    let depth = 0;
    for (let n = target; n && n !== document.body && depth < 12; n = n.parentElement, depth++) {
      if (n.closest && n.closest('.sh-root')) return null;
      if (n.id && byId.has(n.id)) return { el: n, topic: pick(byId.get(n.id)) };
      if (/^(BUTTON|SUMMARY|LABEL|A|H1|H2|H3|H4|LEGEND|TH|SPAN|B)$/.test(n.tagName) || (n.classList && n.classList.contains('lbl'))) {
        const hit = byLabel.get(norm(n.textContent).slice(0, 80));
        if (hit) return { el: n, topic: pick(hit) };
      }
    }
    return { el: null, topic: overview() };
  }

  function outline(el) {
    if (outlined === el) return;
    if (outlined) outlined.classList.remove('sh-target');
    outlined = el;
    if (el) el.classList.add('sh-target');
  }
  function onMove(e) {
    if (!explaining || !data) return;
    const now = Date.now();
    if (now - lastMove < 60) return;
    lastMove = now;
    const hit = resolve(e.target);
    outline(hit && hit.el);
  }
  function onClick(e) {
    if (!explaining && !pendingExplain) return;
    if (e.target.closest && e.target.closest('.sh-root')) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (!data) return;
    const hit = resolve(e.target);
    stopExplain();
    if (hit && hit.topic) show(hit.topic);
  }

  function startExplain() {
    if (explaining || pendingExplain) return;
    close();
    const ticket = ++opening;
    pendingExplain = true;
    button.setAttribute('aria-pressed', 'true');
    load().then(() => {
      if (ticket !== opening) return;
      pendingExplain = false;
      explaining = true;
      document.body.classList.add('sh-explaining');
      button.setAttribute('aria-pressed', 'true');
      hint = node('div', { class: 'sh-root sh-hint', role: 'status' },
        node('span', { text: 'Tap or click a feature, or focus it and press Enter. Esc exits help.' }),
        node('button', { class: 'btn', type: 'button', text: 'Browse all topics', onclick: () => { stopExplain(); browse(); } }),
        node('button', { class: 'btn ghost', type: 'button', text: 'Exit', onclick: stopExplain }));
      document.body.append(hint);
    }).catch(() => { if (ticket === opening) { stopExplain(); notice('The help topics could not be loaded. Reload the page and try again.'); } });
  }
  function stopExplain() {
    opening++;
    pendingExplain = false; pendingPanel = false;
    explaining = false;
    document.body.classList.remove('sh-explaining');
    button.setAttribute('aria-pressed', 'false');
    outline(null);
    if (hint) { hint.remove(); hint = null; }
  }

  function sheet(title, ...body) {
    close();
    opener = document.activeElement;
    const shut = node('button', { class: 'btn ghost sh-close', type: 'button', 'aria-label': 'Close help', text: '×', onclick: close });
    panel = node('aside', { class: 'sh-root sh-panel', role: 'dialog', 'aria-label': title },
      node('header', { class: 'sh-head' }, node('h2', { text: title }), shut), node('div', { class: 'sh-body' }, ...body));
    document.body.append(panel);
    shut.focus();
  }
  function close() {
    opening++; pendingPanel = false;
    if (panel) { panel.remove(); panel = null; }
    if (opener && opener.focus && document.contains(opener)) opener.focus();
    opener = null;
  }

  function loadExample(text) {
    const currentPanel = panel;
    let waits = 0;
    const put = () => {
      if (panel !== currentPanel) return;
      const ta = document.getElementById('sySrc');
      if (!ta) {
        if (++waits < 40) { setTimeout(put, 50); return; }
        notice('Open the Write tab, then load the example again.'); return;
      }
      if (ta.value.trim() && !window.confirm('Replace the program in the editor with this example?')) return;
      ta.value = text;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      close();
    };
    if (window.Studio && typeof window.Studio.go === 'function') window.Studio.go('write');
    setTimeout(put, 0);
  }
  function example(text, program) {
    const kids = [node('pre', { class: 'sh-code', text })];
    // Only explicit, independently checked payloads are executable examples.
    // Prose, arrows, code fences and headings in the displayed explanation are
    // never guessed into source or stripped from a paper.
    if (program && program.checked_profile === 'verified' && ['symblic', 'paper'].includes(program.format) &&
        typeof program.source === 'string' && program.source.length > 0 && program.source.length <= 12000 &&
        typeof program.sha256 === 'string' && /^[a-f0-9]{64}$/.test(program.sha256)) {
      const source = program.source;
      kids.push(node('details', { class: 'sh-sources' },
        node('summary', { text: 'Exact example to load' }), node('pre', { class: 'sh-code', text: source })));
      kids.push(node('button', { class: 'btn', type: 'button', text: 'Load into editor', onclick: async () => {
        const currentPanel = panel;
        try {
          const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(source));
          const sha = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
          if (sha !== program.sha256) { notice('This example does not match its checked source. Reload the help.'); return; }
          if (panel !== currentPanel) return;
          loadExample(source);
        } catch (_) { notice('The checked example could not be verified. Reload the help.'); }
      } }));
    }
    return node('div', { class: 'sh-example' }, ...kids);
  }


  function show(topic) {
    const body = [node('p', { class: 'sh-meta', text: (topic.tab ? 'Tab: ' + topic.tab : topic.group) + ' · ' + topic.id })];
    for (const [name, text] of topic.sections) {
      body.push(node('h3', { text: name }));
      body.push(name === 'Example' ? example(text, topic.load_example) : node('p', { class: 'sh-text', text }));
    }
    if (topic.doubts) body.push(node('p', { class: 'sh-doubt', text: 'Not fully verified: ' + topic.doubts }));
    const related = topic.related.map((id) => byTopic.get(id)).filter(Boolean);
    if (related.length) {
      body.push(node('h3', { text: 'Related' }));
      body.push(node('div', { class: 'sh-related' }, ...related.map((t) =>
        node('button', { class: 'chip', type: 'button', text: t.title, onclick: () => show(t) }))));
    }
    if (topic.sources.length || topic.where) {
      body.push(node('details', { class: 'sh-sources' }, node('summary', { text: 'Where this lives in the code' }),
        node('p', { class: 'sh-text sh-mono', text: [topic.where, ...topic.sources].filter(Boolean).join('\n') })));
    }
    body.push(node('button', { class: 'btn ghost', type: 'button', text: 'All topics', onclick: browse }));
    sheet(topic.title, ...body);
  }

  function browse() {
    stopExplain();
    const ticket = ++opening; pendingPanel = true;
    load().then(() => {
      if (ticket !== opening) return;
      pendingPanel = false;
      const list = node('div', { class: 'sh-list' });
      const search = node('input', { class: 'field sh-search', type: 'search', placeholder: 'Search the help', 'aria-label': 'Search the help' });
      const render = () => {
        list.replaceChildren();
        const q = norm(search.value);
        if (!q) {
          list.append(node('h3', { text: 'Start here (from zero)' }));
          data.path.forEach((id, i) => { const t = byTopic.get(id); if (t) list.append(entry(t, (i + 1) + '. ')); });
        }
        const groups = new Map();
        for (const t of data.topics) {
          if (q && !norm(t.title + ' ' + t.id + ' ' + t.sections.map((s) => s[1]).join(' ')).includes(q)) continue;
          const g = t.tab ? 'Tab: ' + t.tab : t.group;
          if (!groups.has(g)) groups.set(g, []);
          groups.get(g).push(t);
        }
        for (const [g, ts] of groups) {
          const box = node('details', { class: 'sh-group' }, node('summary', { text: g + ' (' + ts.length + ')' }));
          if (q || g === 'Tab: ' + tab()) box.open = true;
          ts.forEach((t) => box.append(entry(t, '')));
          list.append(box);
        }
        if (q && !groups.size) list.append(node('p', { class: 'sh-text', text: 'No topic matches. Try another word.' }));
      };
      search.addEventListener('input', render);
      render();
      sheet('Symblic help', search, list);
      search.focus();
    }).catch(() => { if (ticket === opening) { pendingPanel = false; notice('The help topics could not be loaded. Reload the page and try again.'); } });
  }
  function entry(t, prefix) {
    return node('button', { class: 'sh-entry', type: 'button', text: prefix + t.title, title: t.id, onclick: () => show(t) });
  }
  function notice(text) {
    if (window.Studio && typeof window.Studio.toast === 'function') window.Studio.toast(text);
    else window.alert(text);
  }

  const button = node('button', { class: 'sh-root sh-fab', type: 'button', 'aria-label': 'Help: explain a feature',
    'aria-pressed': 'false', title: 'Help (F1)', text: '?', onclick: () => (explaining || pendingExplain ? stopExplain() : startExplain()) });
  document.addEventListener('pointermove', onMove, { passive: true });
  document.addEventListener('click', onClick, true);
  const ownControl = target => target.closest && target.closest('.sh-root');
  // Suppress page shortcut/submit handlers in the capture phase, before the
  // editor's Ctrl/Meta+Enter handler can dispatch a run or preview.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (explaining || pendingExplain || pendingPanel || panel)) {
      e.preventDefault(); e.stopImmediatePropagation(); stopExplain(); close(); return;
    }
    if (e.key === 'F1') { e.preventDefault(); e.stopImmediatePropagation(); browse(); return; }
    if ((!explaining && !pendingExplain) || ownControl(e.target)) return;
    if (['Tab', 'Shift', 'Control', 'Meta', 'Alt'].includes(e.key)) return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (data && (e.key === 'Enter' || e.key === ' ')) {
      const hit = resolve(e.target); stopExplain(); if (hit && hit.topic) show(hit.topic);
    }
  }, true);
  document.addEventListener('submit', (e) => {
    if ((explaining || pendingExplain) && !ownControl(e.target)) {
      e.preventDefault(); e.stopImmediatePropagation();
    }
  }, true);
  document.addEventListener('pointerdown', (e) => {
    if ((explaining || pendingExplain) && !ownControl(e.target)) {
      e.preventDefault(); e.stopImmediatePropagation();
    }
  }, true);
  document.addEventListener('touchstart', (e) => {
    if ((explaining || pendingExplain) && !ownControl(e.target)) e.stopImmediatePropagation();
  }, { capture: true, passive: true });
  const mount = () => document.body.append(button);
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
  window.SymblicHelp = { browse, explain: startExplain, show: (id) => { stopExplain(); const ticket = ++opening; pendingPanel = true; return load().then(() => { if (ticket !== opening) return; pendingPanel = false; const t = byTopic.get(id); if (t) show(t); }).catch(() => { if (ticket === opening) { pendingPanel = false; notice('The help topics could not be loaded. Reload the page and try again.'); } }); } };
})();
