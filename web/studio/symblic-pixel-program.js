/* One accepted model-built frame at a time. Trusted interpreter and pixel copy only. */
(function (global) {
  'use strict';
  const ABI = Object.freeze(['delta', 'square', 'separation', 'inside', 'nextX', 'bounds', 'whitePixels', 'clearPixels', 'drawPixels']);
  const DEPENDENCIES = Object.freeze({ delta: [], square: [], separation: ['square'], inside: ['delta', 'separation'], nextX: [], bounds: [], whitePixels: ['bounds', 'inside'], clearPixels: [], drawPixels: ['whitePixels'] });
  const DELAY = 1000 / 60;
  const INTEGRITY = typeof document === 'object' ? document.currentScript?.integrity || null : null;
  const PARSER_INTEGRITY = typeof document === 'object' ? document.querySelector('script[src="/symblic_js_contract_acorn.js"]')?.integrity || null : null;
  const owners = new WeakMap();
  function fail(text) { throw new Error(text); }
  function assetContract(assets) {
    if (!assets || Object.keys(assets).length !== 3) fail('The pixel runtime asset contract is missing. Rebuild this saved program.');
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    for (const name of ['parser', 'vm', 'presenter']) {
      const asset = assets[name];
      if (!asset || !/^[a-f0-9]{64}$/.test(asset.sha256 || '')) fail('The pixel runtime asset identity is invalid.');
      const bits = [...asset.sha256].map(value => parseInt(value, 16).toString(2).padStart(4, '0')).join('');
      const sri = 'sha256-' + bits.match(/.{1,6}/g).map(value => alphabet[parseInt(value.padEnd(6, '0'), 2)]).join('') + '=';
      if (asset.sri !== sri) fail('The pixel runtime hash and integrity do not agree.');
    }
  }
  function validate(presentation, outputs) {
    if (!presentation || presentation.kind !== 'binary-pixel-program' || presentation.version !== 1 ||
        !Number.isInteger(presentation.width) || !Number.isInteger(presentation.height) ||
        presentation.width < 1 || presentation.height < 1 || presentation.width > 2048 || presentation.height > 2048 ||
        presentation.width * presentation.height > 480000 || !Number.isInteger(presentation.center_y) ||
        presentation.center_y < 0 || presentation.center_y >= presentation.height ||
        !Number.isInteger(presentation.radius) || presentation.radius < 1 || presentation.radius > 16 ||
        !Number.isInteger(presentation.initial_x) || presentation.initial_x < 0 || presentation.initial_x >= presentation.width ||
        presentation.implementation_label !== 'implementation.js' ||
        presentation.delay_seconds?.numerator !== 1 || presentation.delay_seconds?.denominator !== 60 ||
        !Array.isArray(presentation.functions) || presentation.functions.length !== ABI.length ||
        ABI.some(name => !presentation.functions.includes(name)) || presentation.future_frame_precomputation !== false ||
        !presentation.dependencies || Object.keys(presentation.dependencies).length !== ABI.length || ABI.some(name =>
          !Array.isArray(presentation.dependencies[name]) || presentation.dependencies[name].length !== DEPENDENCIES[name].length ||
          DEPENDENCIES[name].some(dep => !presentation.dependencies[name].includes(dep)))) fail('The saved pixel program has an unsupported presentation contract.');
    if (presentation.min_delay_ms !== DELAY || presentation.buffer?.format !== 'binary-row-major' ||
        presentation.buffer.off !== 0 || presentation.buffer.on !== 1 || presentation.buffer.count !== presentation.width * presentation.height ||
        JSON.stringify(presentation.color?.black) !== '[0,0,0]' || JSON.stringify(presentation.color?.white) !== '[255,255,255]' ||
        presentation.color?.alpha !== 255 || JSON.stringify(presentation.sequence) !== '["compute_column","clear","draw","present","presentation_opportunity","delay"]')
      fail('The saved pixel representation or sequence does not match this presenter.');
    assetContract(presentation.assets);
    if (!Array.isArray(outputs) || outputs.length > 10000) fail('The saved outputs are unavailable.');
    const implementations = outputs.filter(row => row?.label === presentation.implementation_label);
    if (implementations.length !== 1 || typeof implementations[0].value !== 'string') fail('Exactly one accepted implementation is required.');
    return implementations[0].value;
  }
  // Injectable controller makes order and timer semantics testable without a browser or model.
  function createController({ machine, present, waitForPaint, clock, schedule, cancelSchedule, width = 800, height = 600, centerY = 300, visible = () => true, onState = () => {}, onFrame = () => {} }) {
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width * height > 480000 || !Number.isInteger(centerY) || centerY < 0 || centerY >= height) fail('Invalid controller dimensions.');
    let previous = null, count = 0, playing = false, phase = 'ready', error = '', destroyed = false;
    let timer = null, cancelPaint = null, generation = 0;
    const buffer = machine.buffer(width * height), trace = [];
    function event(kind, extra = {}) { trace.push({ kind, time: clock(), ...extra }); if (trace.length > 96) trace.shift(); }
    function state() { return { playing, phase, error, frame: count, x: previous, trace: trace.map(row => ({ ...row })) }; }
    function notify() { onState(state()); }
    function cancel() {
      generation++;
      if (timer !== null) cancelSchedule(timer);
      timer = null; if (cancelPaint) cancelPaint(); cancelPaint = null;
    }
    function pause(reason = '') { if (destroyed) return; cancel(); playing = false; if (phase !== 'error') phase = count ? 'paused' : 'ready'; event('pause', { reason }); notify(); }
    function stopped(errorValue) { cancel(); playing = false; phase = 'error'; error = errorValue?.message || String(errorValue); event('error'); notify(); }
    function delay(token) {
      if (token !== generation || destroyed || !playing) return;
      cancelPaint = null;
      const began = clock(); phase = 'waiting'; event('render-opportunity'); notify();
      function check() {
        timer = null;
        if (token !== generation || destroyed || !playing) return;
        if (!visible()) { pause('not visible'); return; }
        const elapsed = clock() - began;
        if (elapsed < DELAY) { timer = schedule(check, Math.max(1, Math.ceil(DELAY - elapsed))); return; }
        event('delay-complete', { elapsed }); compute();
      }
      timer = schedule(check, Math.ceil(DELAY));
    }
    function barrier() {
      if (!playing || destroyed) return;
      const token = generation; phase = 'presenting'; notify();
      try { cancelPaint = waitForPaint(() => delay(token), errorValue => { if (token === generation) stopped(errorValue); }); }
      catch (errorValue) { stopped(errorValue); }
    }
    function compute() {
      if (destroyed || !playing) return;
      if (!visible()) { pause('not visible'); return; }
      try {
        phase = 'computing'; event('compute'); notify();
        const next = machine.call('nextX', [previous]);
        if (!Number.isInteger(next) || next < 0 || next >= width) fail('The model returned an invalid horizontal position.');
        event('clear');
        if (machine.call('clearPixels', [buffer]) !== buffer || buffer.some(value => value !== 0)) fail('The model did not clear the complete buffer.');
        event('draw');
        if (machine.call('drawPixels', [buffer, next, centerY]) !== buffer || buffer.some(value => value !== 0 && value !== 1)) fail('The model returned an invalid binary buffer.');
        present(buffer); event('copy'); previous = next; count++;
        onFrame({ frame: count, x: previous }); barrier();
      } catch (errorValue) { stopped(errorValue); }
    }
    function play() {
      if (destroyed || playing || error || phase === 'error' || !visible()) return;
      playing = true; event('play');
      // A resumed frame must get its own presentation opportunity and full wait.
      // Never compute a later frame merely because Pause cancelled its earlier wait.
      if (count) barrier(); else compute();
    }
    function destroy() { if (destroyed) return; cancel(); playing = false; destroyed = true; phase = 'destroyed'; }
    return Object.freeze({ play, pause, destroy, state });
  }
  function node(tag, text, className) {
    const item = document.createElement(tag); if (text) item.textContent = text; if (className) item.className = className; return item;
  }
  function mount(target, presentation, outputs) {
    owners.get(target)?.destroy(); target.replaceChildren();
    let machine;
    try {
      const source = validate(presentation, outputs);
      if (!global.SymblicPixelVM) fail('The pixel interpreter is unavailable. Reload this page.');
      const loaded = { parser: PARSER_INTEGRITY, vm: global.SymblicPixelVM.integrity, presenter: INTEGRITY };
      for (const name of Object.keys(loaded)) if (!loaded[name] || presentation.assets[name].sri !== loaded[name])
        fail('The saved program requires different pixel runtime assets. Reload the page or rebuild the program.');
      machine = global.SymblicPixelVM.compile(source, { exports: ABI, dependencies: DEPENDENCIES });
    } catch (error) { const message = node('p', error.message, 'hint'); message.setAttribute('role', 'alert'); target.append(message); return null; }
    const WIDTH = presentation.width, HEIGHT = presentation.height;
    const dialog = node('dialog', '', 'sy-pixels-dialog'), launch = node('button', 'Open display', 'btn');
    launch.type = 'button';
    const outsideStatus = node('p', 'The accepted program is ready to run on this device.', 'hint');
    const root = node('section', '', 'unit sy-pixels'), heading = node('h2', 'Live pixel program');
    const viewport = node('div', '', 'sy-pixels-viewport'), canvas = node('canvas');
    canvas.width = WIDTH; canvas.height = HEIGHT; canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', `${WIDTH} by ${HEIGHT} binary pixels. The accepted program has not started.`);
    viewport.append(canvas);
    const controls = node('div', '', 'sy-pixels-controls'), toggle = node('button', 'Start exact display', 'btn');
    toggle.type = 'button'; const status = node('span', 'Ready', 'sy-pixels-status'); status.setAttribute('aria-live', 'off');
    const preview = node('button', 'Run preview', 'btn ghost'), close = node('button', 'Close display', 'btn ghost'); preview.type = 'button'; close.type = 'button';
    const exact = node('button', 'Use exact display', 'btn ghost'); exact.type = 'button'; exact.hidden = true;
    controls.append(toggle, preview, exact, close, status);
    const sizing = node('p', '', 'hint'), limits = node('p', 'Each frame runs the accepted model functions on this device. The canvas has exact binary buffer pixels; its surrounding browser window is larger. Physical light output, operating-system window size and completed hardware refresh remain unverified.', 'hint');
    const details = node('details'), summary = node('summary', 'Display evidence'), evidence = node('pre'); details.append(summary, evidence);
    root.append(heading, viewport, controls, sizing, limits, details); dialog.append(root); target.append(launch, outsideStatus, dialog);
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) { target.replaceChildren(node('p', 'This browser cannot create the pixel canvas.', 'hint')); return null; }
    ctx.imageSmoothingEnabled = false;
    const image = ctx.createImageData(WIDTH, HEIGHT);
    // No model algorithm lives here: expand accepted binary values to the requested RGB channels.
    function present(buffer) {
      const rgba = image.data;
      for (let i = 0; i < buffer.length; i++) {
        const offset = i * 4, channel = buffer[i] * 255;
        rgba[offset] = channel; rgba[offset + 1] = channel; rgba[offset + 2] = channel; rgba[offset + 3] = 255;
      }
      ctx.putImageData(image, 0, 0);
    }
    let disposed = false, box = null, mapping = 'unmeasured', fits = false, ratio = 1, geometry = null;
    let confirmed = false, displayMode = 'exact', pendingExact = false;
    let observer = null, mutations = null, intersection = null, checkTimer = null, controller;
    const motion = global.matchMedia('(prefers-reduced-motion: reduce)');
    function receipt() { return { version: 1, assets: JSON.parse(JSON.stringify(presentation.assets)), buffer: { width: WIDTH, height: HEIGHT, colors: 'black_or_white', antialiasing: false },
      presentation: { device_pixel_box: box, device_pixel_ratio: ratio, mapping, fits, geometry, mode: displayMode, browser_mapping_confirmed: confirmed,
        viewport_scope: 'canvas_within_browser_window', operating_system_window_size: 'unverified', physical_light: 'unverified', physical_refresh_completion: 'unverified' },
      timing: { minimum_delay_ms: DELAY, clock: 'performance.now', start: 'after_browser_rendering_opportunity', hardware_timer: 'unverified' },
      execution: controller?.state() || null }; }
    function updateEvidence() { if (details.open) evidence.textContent = JSON.stringify(receipt(), null, 2); }
    details.addEventListener('toggle', updateEvidence);
    function visible() {
      if (disposed || !root.isConnected || document.hidden || !dialog.open || !dialog.matches(':modal') || (displayMode === 'exact' && (!fits || !confirmed))) return false;
      const r = canvas.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.left >= -0.5 && r.top >= -0.5 && r.right <= global.innerWidth + 0.5 && r.bottom <= global.innerHeight + 0.5;
    }
    function inspectGeometry() {
      const rect = canvas.getBoundingClientRect(), origin = [rect.left * ratio, rect.top * ratio];
      let transformed = false; const modal = dialog.matches(':modal');
      for (let item = canvas; item instanceof Element; item = item.parentElement) {
        const style = getComputedStyle(item);
        if (style.transform !== 'none' || style.filter !== 'none' || style.perspective !== 'none' || style.opacity !== '1' || style.mixBlendMode !== 'normal' ||
            (style.backdropFilter && style.backdropFilter !== 'none') ||
            (style.zoom && style.zoom !== '1' && style.zoom !== 'normal')) transformed = true;
        // A modal dialog is in the top layer, outside its document ancestors'
        // transform/stacking contexts. Inspect the complete actual display subtree.
        if (item === dialog && modal) break;
      }
      // CSS layout may quantize coordinates by a small fraction of a CSS pixel.
      // This is an origin estimate, never physical pixel attestation.
      return { device_origin_estimate: origin, integral_origin_estimate: origin.every(value => Math.abs(value - Math.round(value)) < 0.08),
        transformed, modal, visual_viewport_scale: global.visualViewport?.scale || 1 };
    }
    function stateChanged(state) {
      toggle.textContent = state.playing ? 'Pause' : state.frame ? (displayMode === 'preview' ? 'Resume preview' : 'Resume display') : 'Start exact display';
      toggle.setAttribute('aria-pressed', String(state.playing)); toggle.disabled = (displayMode === 'exact' && (!fits || !confirmed)) || state.phase === 'error';
      preview.disabled = state.playing || state.phase === 'error';
      exact.hidden = displayMode !== 'preview'; exact.disabled = state.phase === 'error';
      heading.textContent = displayMode === 'preview' ? 'Pixel preview · display scaling unverified' : 'Live pixel program';
      outsideStatus.textContent = state.error || (state.frame ? 'The current frame is retained on this device. Open the display to continue.' : 'The accepted program is ready to run on this device.');
      root.dataset.phase = state.phase; root.dataset.frame = String(state.frame); root.dataset.x = state.x == null ? '' : String(state.x);
      status.textContent = state.error || (state.frame ? `Frame ${state.frame} · center column ${state.x} · ${state.phase}` : state.phase === 'ready' ? 'Ready' : state.phase);
      updateEvidence();
    }
    function waitForPaint(done, rejected) {
      let first = null, second = null, ended = false;
      const watchdog = setTimeout(() => { cancel(); rejected(new Error('No browser rendering opportunity arrived. The display is stopped.')); }, 1500);
      function cancel() { ended = true; clearTimeout(watchdog); if (first !== null) cancelAnimationFrame(first); if (second !== null) cancelAnimationFrame(second); }
      // Callbacks bracket one rendering opportunity; they do not attest physical scanout.
      // The watchdog and all layout/lifecycle decisions remain timer/synchronous based.
      first = requestAnimationFrame(() => {
        if (ended) return;
        second = requestAnimationFrame(() => { if (!ended) { cancel(); done(); } });
      });
      return cancel;
    }
    controller = createController({ machine, present, waitForPaint, width: WIDTH, height: HEIGHT, centerY: presentation.center_y, clock: () => performance.now(), schedule: setTimeout, cancelSchedule: clearTimeout, visible,
      onState: stateChanged, onFrame: value => canvas.setAttribute('aria-label', `${WIDTH} by ${HEIGHT} binary pixels. Frame ${value.frame}. Center column ${value.x}, row ${presentation.center_y}.`) });
    function measure() {
      if (disposed) return;
      controller.pause('display geometry changed'); pendingExact = false;
      ratio = global.devicePixelRatio || 1;
      const zoom = global.visualViewport?.scale || 1, available = viewport.clientWidth;
      const desired = WIDTH / ratio;
      fits = Number.isFinite(ratio) && ratio > 0 && available + 0.1 >= desired && zoom === 1;
      const outer = viewport.getBoundingClientRect();
      const roomHeight = Math.max(1, global.innerHeight - outer.top - 76);
      fits = fits && HEIGHT / ratio <= roomHeight;
      const width = Math.min(desired, Math.max(1, available), roomHeight * WIDTH / HEIGHT);
      canvas.style.width = width + 'px'; canvas.style.height = width * HEIGHT / WIDTH + 'px';
      canvas.style.marginLeft = (Math.ceil(outer.left * ratio) / ratio - outer.left + Math.max(0, Math.floor((available - width) * ratio / 2) / ratio)) + 'px';
      canvas.style.marginRight = '0';
      viewport.style.paddingTop = (Math.ceil(outer.top * ratio) / ratio - outer.top) + 'px';
      geometry = inspectGeometry();
      fits = fits && geometry.modal && !geometry.transformed && geometry.integral_origin_estimate;
      box = null; confirmed = false; mapping = fits ? 'estimated_from_device_pixel_ratio' : 'scaled_preview_only';
      sizing.textContent = fits ? `Canvas buffer: ${WIDTH} × ${HEIGHT}. Waiting for confirmed browser device-pixel sizing. Run preview is available without that confirmation.` : 'The exact canvas does not fit at this zoom. Run preview uses the same accepted program and binary buffer with display scaling; physical pixel obligations remain unmet.';
      stateChanged(controller.state());
      // A same-size canvas does not trigger another resize notification by itself.
      // Re-observe to obtain a fresh browser-reported box after every mapping check.
      if (observer) { observer.unobserve(canvas); observeCanvas(); }
    }
    function checkVisible() {
      const current = inspectGeometry();
      if (JSON.stringify(current) !== JSON.stringify(geometry)) {
        geometry = current;
        if (!current.modal || current.transformed || !current.integral_origin_estimate || current.visual_viewport_scale !== 1) {
          controller.pause('canvas mapping changed'); fits = false; confirmed = false; pendingExact = false; mapping = 'geometry_changed'; stateChanged(controller.state());
        }
      }
      if (!visible() && controller.state().playing) controller.pause('canvas is not fully visible');
    }
    function changed(records) {
      if (!root.isConnected) { destroy(); return; }
      // Status/evidence text changes do not alter the canvas ancestry.
      if (records && !records.some(record => record.target instanceof Element &&
          (record.target === canvas || record.target.contains(canvas)))) return;
      checkVisible();
    }
    function resized() { measure(); }
    function hidden(event) { if (document.hidden || event?.type === 'pagehide') controller.pause('page is hidden'); }
    function reduced() { if (motion.matches) controller.pause('reduced motion requested'); }
    function destroy() {
      if (disposed) return; disposed = true; controller.destroy();
      if (checkTimer !== null) clearInterval(checkTimer);
      observer?.disconnect(); mutations?.disconnect(); intersection?.disconnect();
      global.removeEventListener('resize', resized); global.removeEventListener('scroll', checkVisible, true);
      global.removeEventListener('pagehide', hidden); document.removeEventListener('visibilitychange', hidden);
      global.visualViewport?.removeEventListener('resize', resized); motion.removeEventListener('change', reduced);
      toggle.onclick = null; preview.onclick = null; exact.onclick = null; launch.onclick = null; close.onclick = null; dialog.removeEventListener('close', dialogClosed); details.removeEventListener('toggle', updateEvidence);
      if (dialog.open) dialog.close(); dialog.remove();
      if (owners.get(target) === handle) owners.delete(target);
    }
    function dialogClosed() { pendingExact = false; controller.pause('display closed'); }
    dialog.addEventListener('close', dialogClosed);
    launch.onclick = () => {
      if (disposed) return;
      try { if (dialog.open && !dialog.matches(':modal')) dialog.close(); if (!dialog.open) dialog.showModal(); measure();
        if (!motion.matches) { if (displayMode === 'preview') controller.play(); else pendingExact = true; }
      }
      catch (error) { outsideStatus.textContent = 'Display could not open: ' + error.message; }
    };
    close.onclick = () => { controller.pause('display closed'); dialog.close(); };
    preview.onclick = () => { pendingExact = false; displayMode = 'preview'; stateChanged(controller.state()); controller.play(); };
    exact.onclick = () => { controller.pause('exact display requested'); displayMode = 'exact'; measure(); pendingExact = true; };
    const handle = Object.freeze({ play: () => controller.play(), pause: () => controller.pause('user'),
      hide: () => { controller.pause('display moved'); if (dialog.open) dialog.close(); }, destroy, receipt });
    owners.set(target, handle); toggle.onclick = () => controller.state().playing ? controller.pause('user') : controller.play();
    stateChanged(controller.state());
    function observeCanvas() { try { observer.observe(canvas, { box: 'device-pixel-content-box' }); } catch (_) { observer.observe(canvas); } }
    if (global.ResizeObserver) {
      observer = new ResizeObserver(entries => {
        if (disposed) return;
        for (const entry of entries) if (entry.target === canvas) {
          const value = entry.devicePixelContentBoxSize?.[0];
          if (value) {
            box = [value.inlineSize, value.blockSize];
            const matched = box[0] === WIDTH && box[1] === HEIGHT; confirmed = matched;
            if (!matched && displayMode === 'exact' && controller.state().playing) controller.pause('device-pixel mapping changed');
            mapping = matched && fits ? 'browser_device_pixel_box_matches' : 'browser_device_pixel_box_mismatch';
            sizing.textContent = matched && fits ? `${WIDTH} × ${HEIGHT} buffer pixels → ${WIDTH} × ${HEIGHT} browser-reported device pixels. Physical monitor mapping remains unverified.` : `Browser reports ${box[0]} × ${box[1]} device pixels for the ${WIDTH} × ${HEIGHT} buffer. Exact display is unavailable; Run preview uses this display scaling and leaves physical obligations unmet.`;
            stateChanged(controller.state());
            if (pendingExact && matched && fits && displayMode === 'exact') { pendingExact = false; controller.play(); }
          }
        }
      });
      observeCanvas();
    }
    mutations = new MutationObserver(changed); mutations.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
    if (global.IntersectionObserver) { intersection = new IntersectionObserver(checkVisible, { threshold: 1 }); intersection.observe(canvas); }
    global.addEventListener('resize', resized); global.addEventListener('scroll', checkVisible, true);
    global.addEventListener('pagehide', hidden); document.addEventListener('visibilitychange', hidden);
    global.visualViewport?.addEventListener('resize', resized); motion.addEventListener('change', reduced);
    checkTimer = setInterval(() => { if ((global.devicePixelRatio || 1) !== ratio) measure(); else changed(); }, 500);
    return handle;
  }
  global.SymblicPixelProgram = Object.freeze({ validate, createController, mount, ABI, DEPENDENCIES });
})(typeof window === 'object' ? window : globalThis);
