/* A small stand-in for the original host's page library (`Studio`), so the hub and the Academy render as static
   files. The host served /studio.js and /studio.css to every page; this repository does not include them. When the
   real library has loaded, this file does nothing. Otherwise it defines the members those pages use:
     Studio.boot({title, pages: [{id, name, sub, grp, render}], onPage, onBoot, footLinks,
                  menuSub, menuNow, compactNav})                                   a menu and one page per hash
     Studio.$(id)                                                                    document.getElementById
     Studio.api(url, body)                                                           fetch JSON (POST with a body)
     Studio.esc(text), Studio.att(text)                                              escape text for HTML / for an attribute
     Studio.toast(message)                                                           a short status message that does not block
     Studio.page                                                                     the current page id
     Studio.standalone                                                               true: this stand-in, not the host's library
   Boot options beyond the first four: menuSub(id) returns a live subtitle for a page (or null), menuNow(element)
   fills a small card at the top of the menu, and compactNav folds the page list behind a button on narrow screens
   and keeps it in view on wide ones (for pages with many sections). The file also sets neutral colours for light and
   dark and a few shared styles (buttons, fields, tables, the toast), so the pages are readable without the host's
   theme. Anything that calls the host API (/api/...) still needs a host; see web/README.md. */
(function () {
  'use strict';
  if (window.Studio) return;

  const css = `:root { --bg1:#fbfaf7; --bg2:#f4f1eb; --bg3:#ebe6dc; --tx1:#1d1b18; --tx2:#3d3a35; --tx3:#6b665d;
    --brd:#d9d3c7; --hair:#e6e1d6; --acc:#d9620c; --acc-tx:#a74a06; --mono:ui-monospace, Menlo, Consolas, monospace;
    --sans:system-ui, -apple-system, 'Segoe UI', sans-serif; --ease:cubic-bezier(.22, 1, .36, 1);
    --ctl:#7d786e; --ok:#2f6f52; --err:#a83f3f; --warn:#7d5b12; --onacc:#140b06; }
  @media (prefers-color-scheme: dark) { :root { --bg1:#171614; --bg2:#1f1d1a; --bg3:#2a2723; --tx1:#f1ede6;
    --tx2:#d6d0c6; --tx3:#a29b8f; --brd:#3a3631; --hair:#2f2c28; --acc:#f08a3c; --acc-tx:#f5a466;
    --ctl:#6e6a62; --ok:#4a9977; --err:#d96a6a; --warn:#b98a2f; --onacc:#140b06; } }
  body { margin:0; background:var(--bg1); color:var(--tx1); font:16px/1.55 system-ui, sans-serif; }
  .ss-shell { display:grid; grid-template-columns:240px minmax(0,1fr); min-height:100vh; }
  .ss-nav { border-right:1px solid var(--brd); padding:18px 14px; background:var(--bg2); }
  .ss-nav h1 { font-size:18px; margin:0 0 14px; }
  .ss-nav a { display:block; padding:8px 10px; border-radius:3px; color:var(--tx2); text-decoration:none; min-height:28px; }
  .ss-nav a[aria-current="page"] { background:var(--bg3); color:var(--tx1); font-weight:600; }
  .ss-nav small { display:block; color:var(--tx3); font-size:12px; }
  .ss-nav .ss-grp { margin:14px 0 4px; font:11px var(--mono); text-transform:uppercase; letter-spacing:.12em; color:var(--tx3); }
  .ss-foot { margin-top:18px; display:flex; flex-wrap:wrap; gap:6px; }
  #stage { padding:24px; max-width:1100px; }
  .unit { border:1px solid var(--brd); border-radius:4px; padding:16px; margin:0 0 16px; background:var(--bg1); }
  .lbl { display:block; font:11px var(--mono); text-transform:uppercase; letter-spacing:.12em; color:var(--tx3); margin-bottom:8px; }
  .hint { color:var(--tx2); margin:6px 0; } .rows { display:grid; gap:8px; } .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .grow { flex:1; min-width:0; } .ttl { font-weight:600; } .sub { color:var(--tx3); font-size:14px; } .mono { font-family:var(--mono); }
  .btn, .chip { display:inline-block; padding:6px 10px; border:1px solid var(--brd); border-radius:3px; color:var(--acc-tx); text-decoration:none; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; } .tblwrap { overflow-x:auto; }
  @media (max-width:760px) { .ss-shell { grid-template-columns:minmax(0,1fr); } .ss-nav { border-right:0; border-bottom:1px solid var(--brd); } }
  button.btn { background:none; font:inherit; cursor:pointer; }
  .btn:disabled { opacity:.45; cursor:default; }
  .field { font:inherit; font-size:16px; color:var(--tx1); background:var(--bg1); border:1px solid var(--ctl); border-radius:3px; padding:6px 8px; }
  table.tbl { width:100%; border-collapse:collapse; font-size:14px; }
  .tbl th { font:11px var(--mono); text-transform:uppercase; letter-spacing:.12em; color:var(--tx3); text-align:left; padding:8px 10px; border-bottom:1px solid var(--brd); }
  .tbl td { padding:8px 10px; border-bottom:1px solid var(--hair); vertical-align:top; }
  #toast { position:fixed; left:50%; bottom:calc(24px + env(safe-area-inset-bottom)); transform:translate(-50%, 20px); z-index:90;
    background:var(--tx1); color:var(--bg1); font:13px/1.45 var(--mono); padding:10px 16px; border-radius:3px; max-width:min(86vw, 480px);
    text-align:center; opacity:0; pointer-events:none; transition:opacity .3s var(--ease), transform .3s var(--ease); }
  #toast.show { opacity:1; transform:translate(-50%, 0); }
  @media (prefers-reduced-motion: reduce) { #toast { transition:none; } }
  @media (pointer: coarse) { .btn { display:inline-flex; align-items:center; min-height:44px; } }
  .ss-navtoggle { display:none; }
  .ss-now { margin:0 0 10px; font-size:14px; }
  .ss-now a { display:inline; padding:0; min-height:0; color:var(--acc-tx); text-decoration:underline; }
  .ss-compact .ss-nav { position:sticky; top:0; align-self:start; height:100vh; overflow-y:auto; box-sizing:border-box; }
  @media (max-width:760px) {
    .ss-compact.ss-shell { grid-template-columns:minmax(0,1fr); }
    .ss-compact .ss-nav { z-index:20; height:auto; max-height:100vh; display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:10px 16px; }
    .ss-compact .ss-nav h1 { flex:1; min-width:0; margin:0; font-size:16px; }
    .ss-compact .ss-navtoggle { display:inline-flex; align-items:center; gap:6px; min-height:44px; max-width:62%; padding:6px 12px;
      font:inherit; font-size:15px; color:var(--tx1); background:var(--bg1); border:1px solid var(--ctl); border-radius:3px; cursor:pointer; }
    .ss-compact .ss-navtoggle span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .ss-compact .ss-navlist { flex-basis:100%; }
    .ss-compact .ss-nav:not(.ss-open) .ss-navlist { display:none; }
    .ss-compact #stage { padding:16px; }
  }`;

  let styled = false;
  function style() {
    if (styled) return;
    styled = true;
    document.head.append(el('style', {}, css));
  }

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
    if (text != null) node.textContent = text;
    return node;
  }

  // One escape for text and for quoted attributes: & < > " and ' all become entities.
  const ENTITIES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ENTITIES[c]);

  let toastTimer = 0;

  const Studio = {
    page: '',
    standalone: true,
    $: (id) => document.getElementById(id),
    esc,
    att: esc,
    toast(message) {
      style();
      let box = document.getElementById('toast');
      if (!box) {
        box = el('div', { id: 'toast', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true' });
        document.body.append(box);
      }
      box.textContent = message == null ? '' : String(message);
      box.classList.add('show');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => box.classList.remove('show'), 2600);
    },
    async api(url, body) {
      const response = await fetch(url, body === undefined ? { cache: 'no-store' }
        : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const value = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(value.error || ('HTTP ' + response.status + ' (this part needs a host; see web/README.md)'));
      return value;
    },
    boot(options) {
      style();
      if (options.title) document.title = options.title;
      const shell = el('div', { class: 'ss-shell' + (options.compactNav ? ' ss-compact' : '') });
      const nav = el('nav', { class: 'ss-nav', 'aria-label': 'Pages' });
      nav.append(el('h1', {}, options.title || ''));
      // compactNav: the list sits in its own block that a button folds on narrow screens.
      let list = nav;
      let toggle = null;
      if (options.compactNav) {
        list = el('div', { class: 'ss-navlist', id: 'ssNavList' });
        toggle = el('button', { type: 'button', class: 'ss-navtoggle', 'aria-expanded': 'false', 'aria-controls': 'ssNavList' });
        toggle.onclick = () => toggle.setAttribute('aria-expanded', String(nav.classList.toggle('ss-open')));
        nav.append(toggle, list);
      }
      if (options.menuNow) {
        const now = el('div', { class: 'ss-now' });
        list.append(now);
        options.menuNow(now);
      }
      const stage = el('main', { id: 'stage' });
      const subs = [];
      let group = null;
      for (const page of options.pages) {
        if (page.grp && page.grp !== group) { group = page.grp; list.append(el('div', { class: 'ss-grp' }, group)); }
        const link = el('a', { href: '#' + page.id, 'data-page': page.id }, page.name);
        if (options.menuSub) {
          const small = el('small', {}, page.sub || '');
          subs.push([page, small]);
          link.append(small);
        } else if (page.sub) link.append(el('small', {}, page.sub));
        list.append(link);
      }
      if (options.footLinks) { const foot = el('div', { class: 'ss-foot' }); foot.innerHTML = options.footLinks; list.append(foot); }
      shell.append(nav, stage);
      document.body.append(shell);
      let shown = null;
      const show = () => {
        const wanted = location.hash.slice(1);
        const page = options.pages.find((p) => p.id === wanted) || options.pages[0];
        // compactNav pages are long: a new section starts at its top, not where the last one was scrolled to.
        if (options.compactNav && shown !== null && shown !== page.id) window.scrollTo(0, 0);
        shown = page.id;
        Studio.page = page.id;
        nav.querySelectorAll('a[data-page]').forEach((a) => a.toggleAttribute('aria-current', a.dataset.page === page.id));
        nav.querySelectorAll('a[data-page]').forEach((a) => { if (a.dataset.page === page.id) a.setAttribute('aria-current', 'page'); });
        for (const [p, small] of subs) small.textContent = options.menuSub(p.id) || p.sub || '';
        if (toggle) {
          toggle.replaceChildren(el('span', {}, 'Pages: ' + page.name), el('b', { 'aria-hidden': 'true' }, '▾'));
          nav.classList.remove('ss-open');
          toggle.setAttribute('aria-expanded', 'false');
        }
        if (options.onPage) options.onPage(page.id);
        try {
          page.render(stage);
        } catch (error) {
          // A section that throws says so instead of leaving the page blank or stale.
          stage.replaceChildren(el('div', { class: 'unit' }, 'This section could not be shown: ' + ((error && error.message) || error)));
          console.error(error);
        }
      };
      window.addEventListener('hashchange', show);
      show();
      if (options.onBoot) options.onBoot();
    },
  };
  window.Studio = Studio;
})();
