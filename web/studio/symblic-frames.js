/* Saved, bounded character-grid outputs. No providers, HTML, scripts or network. */
(() => {
  'use strict';
  const PALETTE = ['#e6ffe9', '#9dffab', '#4aef72', '#28c954', '#169a3a', '#11752d', '#0c5421', '#083818'];
  const owners = new WeakMap();
  function validate(outputs) {
    const frames = [];
    let total = 0;
    const bad = () => ({ frames: [], error: 'Character-grid playback unavailable: a frame exceeds the supported format or limits.' });
    if (!Array.isArray(outputs) || outputs.length > 10000) return bad();
    for (const output of outputs) {
      const f = output && output.value;
      if (!f || f.kind !== 'character-grid') continue;
      if (frames.length >= 128 || !Number.isInteger(f.width) || !Number.isInteger(f.height) ||
          f.width < 1 || f.height < 1 || f.width > 100 || f.height > 100 || f.width * f.height > 2500 ||
          !Number.isInteger(f.tick) || f.tick < 0 || f.tick > 63 || !Array.isArray(f.cells) ||
          f.cells.length > f.width * f.height || (total += f.cells.length) > 160000) return bad();
      const seen = new Set(), cells = [];
      for (const c of f.cells) {
        if (!c || !Number.isInteger(c.x) || !Number.isInteger(c.y) || c.x < 0 || c.x >= f.width ||
            c.y < 0 || c.y >= f.height || !Number.isInteger(c.shade) || c.shade < 0 || c.shade > 7 ||
            typeof c.char !== 'string' || c.char.length < 1 || c.char.length > 2 ||
            Array.from(c.char).length !== 1 || (c.char.codePointAt(0) >= 0xd800 && c.char.codePointAt(0) <= 0xdfff)) return bad();
        const key = c.y * f.width + c.x;
        if (seen.has(key)) return bad();
        seen.add(key); cells.push({ x: c.x, y: c.y, char: c.char, shade: c.shade });
      }
      frames.push({ width: f.width, height: f.height, tick: f.tick, cells });
    }
    return { frames, error: null };
  }
  function node(tag, text, className) {
    const n = document.createElement(tag);
    if (text) n.textContent = text;
    if (className) n.className = className;
    return n;
  }
  function mount(target, outputs) {
    if (!target) return null;
    const previous = owners.get(target);
    if (previous) previous.destroy();
    target.replaceChildren();
    const checked = validate(outputs);
    if (checked.error) {
      const error = node('p', checked.error, 'hint'); error.setAttribute('role', 'status');
      target.append(error); return null;
    }
    const frames = checked.frames;
    if (!frames.length) return null;
    const root = node('section', '', 'unit sy-frames');
    const title = node('h2', 'Character-grid playback');
    const canvas = node('canvas'); canvas.setAttribute('role', 'img');
    const controls = node('div', '', 'sy-frames-controls');
    const toggle = node('button', 'Play', 'btn'); toggle.type = 'button';
    const next = node('button', 'Next frame', 'btn ghost'); next.type = 'button';
    const status = node('span', '', 'sy-frames-status');
    const hint = node('p', 'Saved frames · 10 frames per second · playback makes no model calls.', 'hint');
    controls.append(toggle, next, status); root.append(title, canvas, controls, hint); target.append(root);
    const context = canvas.getContext('2d');
    if (!context) { target.replaceChildren(node('p', 'Canvas playback is unavailable in this browser.', 'hint')); return null; }
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let index = 0, playing = false, timer = null, destroyed = false;
    let observer = null, intersection = null;
    function sync() {
      toggle.textContent = playing ? 'Pause' : 'Play';
      toggle.setAttribute('aria-pressed', String(playing));
      toggle.disabled = frames.length < 2; next.disabled = frames.length < 2;
      root.dataset.playing = String(playing); root.dataset.frame = String(index);
      status.textContent = `Frame ${index + 1} of ${frames.length} · tick ${frames[index].tick}`;
    }
    function draw() {
      const frame = frames[index], ratio = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
      const width = frame.width * 18, height = frame.height * 24;
      if (canvas.width !== width * ratio || canvas.height !== height * ratio) {
        canvas.width = width * ratio; canvas.height = height * ratio;
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.fillStyle = '#020805'; context.fillRect(0, 0, width, height);
      context.font = '20px ui-monospace, "SFMono-Regular", Consolas, monospace';
      context.textAlign = 'center'; context.textBaseline = 'middle';
      for (const cell of frame.cells) {
        context.fillStyle = PALETTE[cell.shade];
        context.fillText(cell.char, cell.x * 18 + 9, cell.y * 24 + 12, 18);
      }
      canvas.setAttribute('aria-label', `Character grid, ${frame.width} columns by ${frame.height} rows. Frame ${index + 1} of ${frames.length}, tick ${frame.tick}, ${frame.cells.length} occupied cells. Coordinates start at the top left.`);
      sync();
    }
    function pause() {
      const changed = playing || timer !== null;
      if (timer !== null) clearTimeout(timer);
      timer = null; playing = false;
      if (!destroyed && changed) sync();
    }
    function visible() { return root.isConnected && !document.hidden && root.getClientRects().length > 0; }
    function step() {
      timer = null;
      if (!root.isConnected) { destroy(); return; }
      if (!visible()) { pause(); return; }
      index = (index + 1) % frames.length; draw();
      if (playing) timer = setTimeout(step, 100);
    }
    function play() {
      if (destroyed || playing || frames.length < 2 || !visible()) return;
      playing = true; sync(); timer = setTimeout(step, 100);
    }
    function advance() { if (destroyed) return; pause(); index = (index + 1) % frames.length; draw(); }
    function visibility() { if (document.hidden) pause(); }
    function motion() { if (reduced.matches) pause(); }
    function changed() {
      if (!root.isConnected) destroy();
      else if (!visible()) pause();
    }
    function destroy() {
      if (destroyed) return;
      pause(); destroyed = true;
      if (observer) observer.disconnect();
      if (intersection) intersection.disconnect();
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', pause);
      reduced.removeEventListener('change', motion);
      toggle.onclick = null; next.onclick = null;
      if (owners.get(target) === handle) owners.delete(target);
    }
    const handle = { play, pause, next: advance, destroy };
    owners.set(target, handle);
    toggle.onclick = () => playing ? pause() : play(); next.onclick = advance;
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', pause);
    reduced.addEventListener('change', motion);
    observer = new MutationObserver(changed);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'style', 'class'] });
    if (window.IntersectionObserver) {
      intersection = new IntersectionObserver(entries => { if (entries.some(entry => !entry.isIntersecting)) pause(); });
      intersection.observe(root);
    }
    draw();
    if (!reduced.matches) play();
    return handle;
  }
  window.SymblicFrames = Object.freeze({ mount, validate });
})();
