/* A small stand-in for the original host's page library (`Studio`), so the hub pages render as static files.
   The host served /studio.js and /studio.css to every page; this repository does not include them. When the
   real library has loaded, this file does nothing. Otherwise it defines the four members the hub uses:
     Studio.boot({title, pages: [{id, name, sub, grp, render}], onPage, footLinks})   a menu and one page per hash
     Studio.$(id)                                                                       document.getElementById
     Studio.api(url, body)                                                              fetch JSON (POST with a body)
     Studio.page                                                                        the current page id
   and a few neutral colours, so the page is readable without the host's theme. Anything that calls the host
   API (/api/...) still needs a host; see web/README.md. */
(function () {
  'use strict';
  if (window.Studio) return;

  const css = `:root { --bg1:#fbfaf7; --bg2:#f4f1eb; --bg3:#ebe6dc; --tx1:#1d1b18; --tx2:#3d3a35; --tx3:#6b665d;
    --brd:#d9d3c7; --hair:#e6e1d6; --acc:#d9620c; --acc-tx:#a74a06; --mono:ui-monospace, Menlo, Consolas, monospace; }
  @media (prefers-color-scheme: dark) { :root { --bg1:#171614; --bg2:#1f1d1a; --bg3:#2a2723; --tx1:#f1ede6;
    --tx2:#d6d0c6; --tx3:#a29b8f; --brd:#3a3631; --hair:#2f2c28; --acc:#f08a3c; --acc-tx:#f5a466; } }
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
  @media (max-width:760px) { .ss-shell { grid-template-columns:1fr; } .ss-nav { border-right:0; border-bottom:1px solid var(--brd); } }`;

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
    if (text != null) node.textContent = text;
    return node;
  }

  const Studio = {
    page: '',
    $: (id) => document.getElementById(id),
    async api(url, body) {
      const response = await fetch(url, body === undefined ? { cache: 'no-store' }
        : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const value = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(value.error || ('HTTP ' + response.status + ' (this part needs a host; see web/README.md)'));
      return value;
    },
    boot(options) {
      document.head.append(el('style', {}, css));
      if (options.title) document.title = options.title;
      const shell = el('div', { class: 'ss-shell' });
      const nav = el('nav', { class: 'ss-nav', 'aria-label': 'Pages' });
      nav.append(el('h1', {}, options.title || ''));
      const stage = el('main', { id: 'stage' });
      let group = null;
      for (const page of options.pages) {
        if (page.grp && page.grp !== group) { group = page.grp; nav.append(el('div', { class: 'ss-grp' }, group)); }
        const link = el('a', { href: '#' + page.id, 'data-page': page.id }, page.name);
        if (page.sub) link.append(el('small', {}, page.sub));
        nav.append(link);
      }
      if (options.footLinks) { const foot = el('div', { class: 'ss-foot' }); foot.innerHTML = options.footLinks; nav.append(foot); }
      shell.append(nav, stage);
      document.body.append(shell);
      const show = () => {
        const wanted = location.hash.slice(1);
        const page = options.pages.find((p) => p.id === wanted) || options.pages[0];
        Studio.page = page.id;
        nav.querySelectorAll('a[data-page]').forEach((a) => a.toggleAttribute('aria-current', a.dataset.page === page.id));
        nav.querySelectorAll('a[data-page]').forEach((a) => { if (a.dataset.page === page.id) a.setAttribute('aria-current', 'page'); });
        if (options.onPage) options.onPage(page.id);
        page.render(stage);
      };
      window.addEventListener('hashchange', show);
      show();
      if (options.onBoot) options.onBoot();
    },
  };
  window.Studio = Studio;
})();
