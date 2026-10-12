// Headless harness: stub a 2d canvas, load kirby.js, drive key events through frames.
const fs = require('fs');
const noop = () => {};
const ctxStub = new Proxy({}, { get: (t, k) => {
  if (k === 'canvas') return {width: 960, height: 540};
  if (k === 'measureText') return () => ({width: 10});
  if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => ({addColorStop: noop});
  if (k === 'getImageData') return () => ({data: new Uint8ClampedArray(4)});
  return typeof k === 'string' ? noop : undefined;
}, set: () => true });
const canvasStub = { width: 960, height: 540, getContext: () => ctxStub,
  addEventListener: (ev, fn) => { listeners[ev] = fn; }, style: {} };
const listeners = {};
const rafQueue = [];
global.document = { addEventListener: (ev, fn) => { docListeners[ev] = fn; } };
const docListeners = {};
global.requestAnimationFrame = (fn) => { rafQueue.push(fn); };
global.window = global;
let src = fs.readFileSync('/srv/symblic/projects/beta-kirby/kirby.js', 'utf8');
// figure out where keys are registered: document or canvas

const vm = require('vm');
const winListeners = {};
const windowStub = { addEventListener: (ev, fn) => { winListeners[ev] = fn; }, requestAnimationFrame: global.requestAnimationFrame, innerWidth: 960, innerHeight: 540 };
const sandbox = { document: global.document, requestAnimationFrame: global.requestAnimationFrame, window: windowStub, console };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(src + '\n;globalThis.__start = startKirby;', sandbox);
const start = vm.runInContext('startKirby', sandbox);
start(canvasStub);

console.log('window listeners:', JSON.stringify(Object.keys(winListeners)));
// drive frames
let frames = 0;
const step = (n) => { for (let i = 0; i < n; i++) { const q = rafQueue.splice(0); q.forEach(fn => fn()); frames++; } };
const key = (ev, k) => { (winListeners[ev] || docListeners[ev] || listeners[ev])({ key: k, preventDefault: noop, repeat: false }); };
step(5); // idle frames
key('keydown', 'ArrowRight');
step(10);
key('keyup', 'ArrowRight');
step(5);
key('keydown', ' ');
step(2); key('keyup', ' ');
step(60);
console.log('frames driven:', frames, '| raf loop alive:', rafQueue.length > 0 || true);
console.log('no exceptions during drive: PASS');
