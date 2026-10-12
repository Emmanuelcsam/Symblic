/* Symblic sub-navigation: one strip on every Symblic page so the tools feel like one subsite.
   Self-contained (styles injected), absolute links, no API calls, no layout decisions on
   requestAnimationFrame. Included with <script src="/symblic/subnav.js" defer>.
   HOST-ONLY: the links are the original host's routes (it served this folder at /symblic/ and web/studio at
   /automation-studio/); no page in this repository includes this script. The host's terminal, Forge and
   Academy pages, which the strip also linked, are not part of this repository. */
(function () {
  'use strict';
  const LINKS = [
    ['/symblic/', 'Symblic'],
    ['/automation-studio/symblic.html#english', 'Language'],
    ['/symblic/beta.html', 'Beta record'],
  ];
  const CSS = '.sy-strip{display:flex;gap:2px;flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;padding:6px var(--pad,20px);' +
    'border-bottom:1px solid var(--hair,#dcd7cd);background:var(--bg1,#f4f1eb);font-family:var(--mono,monospace);font-size:11px;' +
    'letter-spacing:.12em;text-transform:uppercase}' +
    '.sy-strip::-webkit-scrollbar{display:none}' +
    '.sy-strip a{color:var(--tx3,#625e56);text-decoration:none;padding:8px 10px;min-height:32px;white-space:nowrap;border-bottom:2px solid transparent}' +
    '.sy-strip a:hover,.sy-strip a:focus-visible{color:var(--tx1,#1a1a1a);outline:none;border-bottom-color:var(--ctl,#7d786e)}' +
    '.sy-strip a[aria-current="page"]{color:var(--acc-tx,#a83c16);border-bottom-color:var(--acc,#ff6b35)}';
  function current(href) {
    const here = location.pathname.replace(/\.html$/, '').replace(/\/$/, '') || '/';
    const there = href.split('#')[0].replace(/\.html$/, '').replace(/\/$/, '') || '/';
    if (there === '/symblic') return here === '/symblic' || here === '/symblic-hub';
    return here === there || (there === '/symblic/beta' && (here === '/symblic-beta' || here === '/symblic/beta'));
  }
  function mount() {
    if (document.querySelector('.sy-strip')) return;
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.append(style);
    const nav = document.createElement('nav');
    nav.className = 'sy-strip';
    nav.setAttribute('aria-label', 'Symblic tools');
    for (const [href, text] of LINKS) {
      const a = document.createElement('a');
      a.href = href;
      a.textContent = text;
      if (current(href)) a.setAttribute('aria-current', 'page');
      nav.append(a);
    }
    const header = document.querySelector('body > header');
    if (header) header.insertAdjacentElement('afterend', nav);
    else document.body.prepend(nav);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
