/* Source-only diagnostics. The caller owns checking and request freshness; no model or parser here. */
(function (root) {
  'use strict';
  const LIMIT = 128;
  let nextId = 0;
  const integer = value => Number.isInteger(value) && value >= 0;
  const low = n => n >= 0xdc00 && n <= 0xdfff;
  const high = n => n >= 0xd800 && n <= 0xdbff;
  function normalize(source, diagnostics) {
    if (typeof source !== 'string' || !Array.isArray(diagnostics)) return [];
    return diagnostics.slice(0, LIMIT).filter(row => row && typeof row === 'object').map(row => {
      let start = row.start, end = row.end;
      let kind = ['token', 'line', 'point', 'none'].includes(row.position_kind) ? row.position_kind : 'none';
      if (!integer(start) || !integer(end) || start > end || end > source.length || kind === 'none') {
        start = end = null; kind = 'none';
      } else {
        // Never render half a surrogate pair, even if a malformed producer splits one.
        if (start > 0 && low(source.charCodeAt(start)) && high(source.charCodeAt(start - 1))) start--;
        if (end > 0 && low(source.charCodeAt(end)) && high(source.charCodeAt(end - 1))) end++;
        if (start === end) kind = 'point';
      }
      return { severity: ['error', 'warning', 'info'].includes(row.severity) ? row.severity : 'info',
        code: typeof row.code === 'string' ? row.code.slice(0, 120) : '',
        message: typeof row.message === 'string' ? row.message.slice(0, 4000) : 'Diagnostic',
        line: integer(row.line) && row.line > 0 ? row.line : null,
        col: integer(row.col) && row.col > 0 ? row.col : null,
        start, end, position_kind: kind };
    });
  }
  function location(row) {
    if (row.position_kind === 'none') return 'Location unavailable';
    const line = row.line ? 'Line ' + row.line : 'Source';
    if (row.position_kind === 'line') return line + ' (whole line; exact portion unavailable)';
    if (row.position_kind === 'point') return line + (row.col ? ', column ' + row.col : '') + ' (insertion point)';
    return line + (row.col ? ', column ' + row.col : '');
  }
  function attach(textarea, options = {}) {
    if (!textarea || textarea.tagName !== 'TEXTAREA' || !textarea.parentElement) throw new TypeError('Attach diagnostics to a mounted textarea.');
    const doc = textarea.ownerDocument, win = doc.defaultView, parent = textarea.parentElement;
    const id = 'sy-editor-diag-' + (++nextId);
    const node = (tag, className, text) => {
      const element = doc.createElement(tag); if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    };
    const originalPosition = parent.style.position;
    const suppliedParentPosition = win.getComputedStyle(parent).position === 'static';
    if (suppliedParentPosition) parent.style.position = 'relative';
    const overlay = node('div', 'sy-editor-overlay'); overlay.setAttribute('aria-hidden', 'true');
    const mirror = node('div', 'sy-editor-mirror'); overlay.append(mirror); parent.append(overlay);
    const ownedProblems = !options.problems;
    const problems = options.problems || node('div', 'sy-editor-problems');
    if (ownedProblems) parent.insertAdjacentElement('afterend', problems);
    problems.classList.add('sy-editor-problems');
    const status = node('p', 'sy-editor-status'); status.id = id;
    status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    const list = node('ol', 'sy-editor-problem-list');
    list.setAttribute('aria-label', options.label || 'Source diagnostics');
    problems.replaceChildren(status, list);
    const described = textarea.getAttribute('aria-describedby');
    textarea.setAttribute('aria-describedby', [described, id].filter(Boolean).join(' '));
    const shortcut = textarea.getAttribute('aria-keyshortcuts');
    textarea.setAttribute('aria-keyshortcuts', [shortcut, 'F8 Shift+F8'].filter(Boolean).join(' '));
    const tooltip = node('div', 'sy-editor-tooltip'); tooltip.id = id + '-tip';
    tooltip.setAttribute('role', 'tooltip'); tooltip.hidden = true; doc.body.append(tooltip);
    let rows = [], source = '', marks = [], selected = -1, destroyed = false;
    const listeners = [];
    const listen = (target, name, callback, opts) => {
      target.addEventListener(name, callback, opts); listeners.push(() => target.removeEventListener(name, callback, opts));
    };
    function hideTip() { tooltip.hidden = true; }
    function message(row) { return row.severity + ': ' + row.message + ' · ' + location(row); }
    function showTip(row, x, y) {
      tooltip.textContent = message(row); tooltip.hidden = false;
      const bounds = tooltip.getBoundingClientRect();
      tooltip.style.left = Math.max(8, Math.min(x + 12, win.innerWidth - bounds.width - 8)) + 'px';
      tooltip.style.top = Math.max(8, Math.min(y + 18, win.innerHeight - bounds.height - 8)) + 'px';
    }
    function sync() {
      mirror.style.transform = 'translate(' + (-textarea.scrollLeft) + 'px,' + (-textarea.scrollTop) + 'px)';
    }
    function refresh() {
      if (destroyed) return;
      const css = win.getComputedStyle(textarea);
      overlay.style.left = (textarea.offsetLeft + textarea.clientLeft) + 'px';
      overlay.style.top = (textarea.offsetTop + textarea.clientTop) + 'px';
      overlay.style.width = textarea.clientWidth + 'px'; overlay.style.height = textarea.clientHeight + 'px';
      const names = ['fontFamily', 'fontSize', 'fontStyle', 'fontWeight', 'fontStretch', 'fontVariant',
        'fontKerning', 'fontFeatureSettings', 'fontVariationSettings', 'lineHeight', 'letterSpacing', 'wordSpacing',
        'textAlign', 'textIndent', 'textTransform', 'direction', 'tabSize',
        'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft'];
      for (const name of names) mirror.style[name] = css[name];
      mirror.style.width = textarea.clientWidth + 'px';
      mirror.style.whiteSpace = textarea.wrap === 'off' ? 'pre' : 'pre-wrap';
      mirror.style.overflowWrap = textarea.wrap === 'off' ? 'normal' : 'break-word';
      mirror.style.wordBreak = css.wordBreak;
      sync();
    }
    function renderMarks() {
      mirror.replaceChildren(); marks = [];
      if (!rows.some(row => row.start !== null)) return;
      const boundaries = [...new Set([0, source.length, ...rows.flatMap(row => row.start === null ? [] : [row.start, row.end])])].sort((a, b) => a - b);
      function point(at) {
        const indices = rows.flatMap((row, index) => row.start === at && row.end === at ? [index] : []);
        if (!indices.length) return;
        const mark = node('span', 'sy-editor-point'); mark.dataset.diagnostic = indices.join(',');
        mark.dataset.severity = rows[indices.find(index => rows[index].severity === 'error') ?? indices[0]].severity;
        mirror.append(mark); marks.push({ node: mark, indices });
      }
      for (let part = 0; part < boundaries.length; part++) {
        const at = boundaries[part], end = boundaries[part + 1]; point(at);
        if (end === undefined || end === at) continue;
        const indices = rows.flatMap((row, index) => row.start !== null && row.start <= at && row.end >= end && row.start !== row.end ? [index] : []);
        const text = source.slice(at, end);
        if (!indices.length) { mirror.append(doc.createTextNode(text)); continue; }
        const mark = node('span', 'sy-editor-mark', text); mark.dataset.diagnostic = indices.join(',');
        mark.dataset.severity = rows[indices.find(index => rows[index].severity === 'error') ?? indices.find(index => rows[index].severity === 'warning') ?? indices[0]].severity;
        mirror.append(mark); marks.push({ node: mark, indices });
      }
      // A final newline needs a real line box, as in a textarea. This does not alter the source.
      if (!source || source.endsWith('\n')) mirror.append(doc.createTextNode('\u200b'));
      refresh();
    }
    function clear(text = '') {
      if (destroyed) return;
      rows = []; source = ''; marks = []; selected = -1;
      mirror.replaceChildren(); list.replaceChildren(); status.textContent = text; hideTip();
    }
    function focus(index) {
      if (destroyed || textarea.value !== source || !Number.isInteger(index) || !rows[index]) return false;
      const row = rows[index]; selected = index;
      if (row.start === null) { status.textContent = message(row); return false; }
      textarea.focus({ preventScroll: true }); textarea.setSelectionRange(row.start, row.end);
      refresh();
      const mark = marks.find(item => item.indices.includes(index));
      if (mark) {
        const rect = mark.node.getBoundingClientRect(), view = overlay.getBoundingClientRect();
        const css = win.getComputedStyle(textarea), pad = parseFloat(css.lineHeight) || 24;
        const scaleX = view.width / textarea.clientWidth || 1, scaleY = view.height / textarea.clientHeight || 1;
        if (rect.top < view.top || rect.bottom > view.bottom) textarea.scrollTop += (rect.top - view.top) / scaleY - pad;
        if (textarea.wrap === 'off' && (rect.left < view.left || rect.right > view.right)) textarea.scrollLeft += (rect.left - view.left) / scaleX - 16;
        sync();
      }
      status.textContent = message(row) + '. F8: next problem. Shift+F8: previous.';
      return true;
    }
    function setDiagnostics(checkedSource, diagnostics) {
      if (destroyed) return false;
      if (typeof checkedSource !== 'string' || checkedSource !== textarea.value) { clear('Source changed. Check it again.'); return false; }
      source = checkedSource; rows = normalize(source, diagnostics); selected = -1; list.replaceChildren(); hideTip();
      const errors = rows.filter(row => row.severity === 'error').length;
      const warnings = rows.filter(row => row.severity === 'warning').length;
      status.textContent = rows.length ? `${errors} error${errors === 1 ? '' : 's'}, ${warnings} warning${warnings === 1 ? '' : 's'}. F8 moves through problems.` : 'No diagnostics reported by this check.';
      if (Array.isArray(diagnostics) && diagnostics.length > LIMIT) status.textContent += ' Showing the first ' + LIMIT + ' diagnostics.';
      rows.forEach((row, index) => {
        const item = node('li'); item.dataset.severity = row.severity;
        const button = node('button', 'sy-editor-problem'); button.type = 'button';
        button.append(node('span', 'sy-editor-problem-severity', row.severity === 'info' ? 'Note' : row.severity === 'error' ? 'Error' : 'Warning'),
          node('span', 'sy-editor-problem-location', location(row)), node('span', '', row.message));
        button.title = message(row); button.dataset.diagnosticIndex = index;
        if (row.start === null) button.setAttribute('aria-disabled', 'true');
        item.append(button); list.append(item);
      });
      renderMarks(); return true;
    }
    listen(list, 'click', event => {
      const button = event.target.closest('button[data-diagnostic-index]');
      if (button && list.contains(button)) focus(Number(button.dataset.diagnosticIndex));
    });
    listen(textarea, 'input', () => clear(rows.length ? 'Source changed. Check it again.' : ''));
    listen(textarea, 'scroll', () => { sync(); hideTip(); }, { passive: true });
    listen(textarea, 'keydown', event => {
      if (event.key !== 'F8' || event.altKey || event.ctrlKey || event.metaKey || !rows.length) return;
      event.preventDefault();
      const step = event.shiftKey ? -1 : 1;
      focus((selected < 0 ? (step > 0 ? 0 : rows.length - 1) : selected + step + rows.length) % rows.length);
    });
    listen(textarea, 'pointermove', event => {
      if (event.pointerType === 'touch' || !rows.length) return;
      for (const mark of marks) {
        for (const rect of mark.node.getClientRects()) {
          if (event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom + 4) {
            const primary = mark.indices.find(index => rows[index].severity === 'error') ?? mark.indices.find(index => rows[index].severity === 'warning') ?? mark.indices[0];
            showTip(rows[primary], event.clientX, event.clientY); return;
          }
        }
      }
      hideTip();
    });
    listen(textarea, 'pointerleave', hideTip); listen(textarea, 'blur', hideTip);
    listen(win, 'resize', refresh); listen(win, 'scroll', hideTip, true);
    const observer = typeof win.ResizeObserver === 'function' ? new win.ResizeObserver(refresh) : null;
    if (observer) { observer.observe(textarea); observer.observe(parent); }
    refresh();
    function destroy() {
      if (destroyed) return;
      destroyed = true; listeners.forEach(remove => remove()); observer?.disconnect(); overlay.remove(); tooltip.remove();
      if (ownedProblems) problems.remove(); else problems.replaceChildren();
      if (suppliedParentPosition && parent.style.position === 'relative') parent.style.position = originalPosition;
      if (described === null) textarea.removeAttribute('aria-describedby'); else textarea.setAttribute('aria-describedby', described);
      if (shortcut === null) textarea.removeAttribute('aria-keyshortcuts'); else textarea.setAttribute('aria-keyshortcuts', shortcut);
      rows = []; marks = [];
    }
    return { setDiagnostics, clear, focus, refresh, destroy };
  }
  const api = Object.freeze({ attach, normalize });
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.SymblicEditorDiagnostics = api;
})(typeof window !== 'undefined' ? window : null);
