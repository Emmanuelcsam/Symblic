"""Checks for the English pixel grammar that run each candidate inside the exact browser pixel interpreter.

What it is for: symblic.english.pixels builds pixel programs whose functions run, in the end, inside a small
JavaScript pixel interpreter shipped with the web studio (web/studio/symblic-pixel-vm.js). This module makes the
kernel test every model-written function the way that interpreter will run it: it loads the pinned parser (acorn,
symblic/js/acorn.js) and the interpreter, checks their SHA-256 against ASSETS (a changed byte refuses the checks
until the hash here is updated on purpose), and generates `js_test` statements in which the candidate source is
passed to the interpreter as quoted data, never executed as a native piece. The harness inspects the interpreter's
results with fixed geometry (white pixels inside the dot, everything else black, wrap-around at the edge).

These are finite construction checks, not independent held-out evidence: they cover the configurations listed in the
harness, nothing more.

Depends on: symblic.kernel.language, symblic.lang.abstraction, and the three pinned asset files.
Used by: symblic.english.pixels.
"""
from __future__ import annotations

_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import base64
import hashlib
import json
import re
from pathlib import Path

from symblic.kernel import language as S
from symblic.lang import abstraction as L

VERSION = 'symblic-english-pixel-checks/2'
INPUT_NAME = 'pixel_vm_boot'
# The exact files the checks run, as paths from the repository root, pinned by sha256: the acorn JavaScript parser
# (vendored with symblic.js) and the browser pixel interpreter and presenter of the web studio. A changed byte in
# any of them refuses the checks (`bootstrap`) until the hash here is updated on purpose.
ASSETS = {
    'parser': ('symblic/js/acorn.js', 'cb3b2d439857d6e4514d23a1219f6354c23498f5fa81fdf2691a5a9e53de43c0'),
    'vm': ('web/studio/symblic-pixel-vm.js', 'aff8958b8d46f35309b4346858e032ca7aa677fb80b37ac5579c3f8ee26ac1b8'),
    'presenter': ('web/studio/symblic-pixel-program.js', '06c80765457f9e55a6728c003f50509ebe6205ffde752ee84fcdc443808c60c3'),
}
DEPENDENCIES = {
    'delta': [], 'square': [], 'separation': ['square'],
    'inside': ['delta', 'separation'], 'nextX': [], 'bounds': [],
    'whitePixels': ['bounds', 'inside'], 'clearPixels': [],
    'drawPixels': ['whitePixels'],
}
ABI = tuple(DEPENDENCIES)

# No implementation function in this harness is exported to the candidate VM.
# Geometry is used only to inspect interpreter results, never as a fallback.
HARNESS = r'''
function pixelCheck(target, names, scenario, phase) {
  "use strict";
  if (scenario === undefined) scenario = 0;
  if (phase === undefined) phase = 0;
  const cfg = PIXEL_CHECK_CONFIG, all = PIXEL_CHECK_DEPENDENCIES;
  if (!Array.isArray(pixelSources) || pixelSources.some(s => typeof s !== 'string') ||
      !Array.isArray(names) || names.length !== pixelSources.length ||
      new Set(names).size !== names.length || names.some(n => !Object.hasOwn(all, n)))
    throw new Error('Client VM gate: invalid quoted source selection.');
  const deps = Object.fromEntries(names.map(n => [n, all[n]]));
  const machine = SymblicPixelVM.compile(pixelSources.join('\n\n'),
    {parser: acorn, exports: names, dependencies: deps});
  const W = cfg.width, H = cfg.height, R = cfg.radius, CY = cfg.center_y, N = W * H;
  function demand(ok, message) {
    if (!ok) throw new Error('Client VM gate ' + target + ': ' + message);
  }
  function same(actual, expected, message) {
    if (typeof actual !== typeof expected || JSON.stringify(actual) !== JSON.stringify(expected))
      throw new Error('Client VM gate ' + target + ': ' + message);
  }
  function white(cx, cy) {
    const values = [];
    for (let y = Math.max(0, cy - R); y <= Math.min(H - 1, cy + R); y++)
      for (let x = Math.max(0, cx - R); x <= Math.min(W - 1, cx + R); x++)
        if ((x - cx) * (x - cx) + (y - cy) * (y - cy) <= R * R) values.push(y * W + x);
    return values;
  }
  const centers = [0, Math.min(1, W - 1), Math.floor((W - 1) / 2), Math.max(0, W - 2), W - 1];
  function checkRaster(buffer, expected, message, pattern = false) {
    const indices = new Set(expected);
    demand(buffer.length === N, 'buffer length changed');
    for (let i = 0; i < N; i++) {
      const wanted = indices.has(i) || (pattern && i % 2 === phase) ? 1 : 0;
      demand(buffer[i] === wanted, message + ' at pixel ' + i);
    }
  }
  function runUnit(name) {
    if (name === 'delta') {
      for (const [a, b] of [[7, 3], [3, 7], [-4, 9], [0, 0]]) same(machine.call(name, [a, b]), a - b, 'signed difference');
    } else if (name === 'square') {
      for (const a of [-5, 0, 4, 11]) same(machine.call(name, [a]), a * a, 'square');
    } else if (name === 'separation') {
      for (const [a, b] of [[3, 4], [-3, -4], [0, 0], [5, -2]]) same(machine.call(name, [a, b]), a * a + b * b, 'squared separation');
    } else if (name === 'inside') {
      for (const [dx, dy] of [[0, 0], [R, 0], [-R, 0], [0, R], [0, -R], [R, 1], [R + 1, 0]])
        same(machine.call(name, [2 + dx, CY + dy, 2, CY]), dx * dx + dy * dy <= R * R, 'inclusive distance boundary');
    } else if (name === 'nextX') {
      same(machine.call(name, [null]), cfg.initial_x, 'initial center');
      for (const x of centers) same(machine.call(name, [x]), x === W - 1 ? 0 : x + 1, 'next center or wrap');
    } else if (name === 'bounds') {
      for (const x of centers) {
        const got = machine.call(name, [x, CY]);
        demand(got !== null && typeof got === 'object' && !Array.isArray(got), 'bounds object');
        same(Object.keys(got).sort(), ['bottom', 'left', 'right', 'top'], 'bounds fields');
        same([got.left, got.right, got.top, got.bottom], [Math.max(0, x - R), Math.min(W - 1, x + R), Math.max(0, CY - R), Math.min(H - 1, CY + R)], 'clipped bounds');
      }
    } else if (name === 'whitePixels') {
      for (const x of centers) same(machine.call(name, [x, CY]), white(x, CY), 'ordered white indices');
    } else if (name === 'clearPixels') {
      const buffer = machine.buffer(N); buffer.fill(1);
      demand(machine.call(name, [buffer]) === buffer, 'clear must return the supplied buffer');
      checkRaster(buffer, [], 'clear every pixel');
    } else if (name === 'drawPixels') {
      demand(Number.isInteger(scenario) && scenario >= 0 && scenario < centers.length && (phase === 0 || phase === 1), 'invalid pattern scenario');
      { const x = centers[scenario];
        const buffer = machine.buffer(N);
        for (let i = 0; i < N; i++) buffer[i] = i % 2 === phase ? 1 : 0;
        demand(machine.call(name, [buffer, x, CY]) === buffer, 'draw must return the supplied buffer');
        checkRaster(buffer, white(x, CY), 'draw must preserve every off-disk pixel', true);
      }
    } else throw new Error('Client VM gate: unknown target.');
  }
  if (target === 'assembly') {
    demand(names.length === Object.keys(all).length, 'incomplete assembly');
    const previousValues = [null, 0, Math.max(0, W - 2), W - 1];
    demand(Number.isInteger(scenario) && scenario >= 0 && scenario < previousValues.length, 'invalid assembly scenario');
    const buffer = machine.buffer(N);
    { const previous = previousValues[scenario];
      const next = machine.call('nextX', [previous]);
      same(next, previous === null ? cfg.initial_x : previous === W - 1 ? 0 : previous + 1, 'sequential center');
      buffer.fill(1);
      demand(machine.call('clearPixels', [buffer]) === buffer, 'clear identity');
      checkRaster(buffer, [], 'sequential clear');
      demand(machine.call('drawPixels', [buffer, next, CY]) === buffer, 'draw identity');
      checkRaster(buffer, white(next, CY), 'sequential raster');
    }
  } else {
    demand(names.includes(target), 'target missing from selected sources');
    runUnit(target);
  }
  return true;
}
'''


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _literal(value):
    return L.literal(S.from_json(value))


def bootstrap(config, *, asset_root=None):
    """Read only exact reviewed source assets; return trusted host input + identity."""
    cfg = {'width': config['width'], 'height': config['height'], 'radius': config['radius'],
           'center_y': config.get('fixed_y', config.get('center_y')), 'initial_x': config.get('initial_x', 0)}
    if (any(type(value) is not int for value in cfg.values()) or
            not 1 <= cfg['width'] <= 2048 or not 1 <= cfg['height'] <= 2048 or
            cfg['width'] * cfg['height'] > 480000 or not 1 <= cfg['radius'] <= 16 or
            not 0 <= cfg['center_y'] < cfg['height'] or not 0 <= cfg['initial_x'] < cfg['width']):
        raise ValueError('Invalid bounded pixel VM check configuration')
    root = Path(asset_root) if asset_root is not None else Path(__file__).resolve().parents[2]   # repository root
    parts, parser_source, identity = [], '', {'version': VERSION}
    for role, (relative, expected) in ASSETS.items():
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError('Pinned pixel check asset is unavailable: ' + relative)
        raw = path.read_bytes()
        if _sha(raw) != expected:
            raise ValueError('Pinned pixel check asset identity changed: ' + relative)
        if role == 'parser':
            parser_source = raw.decode('utf-8')
        elif role == 'vm':
            parts.append(raw.decode('utf-8'))
        identity[role] = {'path': relative, 'sha256': expected,
                          'sri': 'sha256-' + base64.b64encode(bytes.fromhex(expected)).decode()}
    settings = ('\nconst PIXEL_CHECK_CONFIG = ' + json.dumps(cfg, separators=(',', ':')) + ';\n'
                'const PIXEL_CHECK_DEPENDENCIES = ' + json.dumps(DEPENDENCIES, separators=(',', ':')) + ';\n')
    boot = '\n'.join(parts) + settings + HARNESS
    if len(boot) > 100000:
        raise ValueError('Trusted pixel check bootstrap exceeds its source budget')
    identity.update(parser_binding='pixel_vm_parser', host_input=INPUT_NAME, harness_sha256=_sha(HARNESS.encode()), bootstrap_sha256=_sha(boot.encode()),
                    bootstrap_characters=len(boot), candidate_execution='quoted_data_to_exact_client_interpreter',
                    clock_scope='Existing deterministic sandbox fixes Date.now; VM syntax, dependency, step and allocation limits plus the outer sandbox timeout are enforced. Device-dependent browser wall time remains unverified.')
    return {'inputs': {INPUT_NAME: boot}, 'parser_source': parser_source, 'assets': identity}


def gate_lines(target, bindings, names, *, retained=False):
    """Generate native statements. Candidate text is encoded by native text(list)."""
    if target not in (*ABI, 'assembly') or len(bindings) != len(names) or not bindings:
        raise ValueError('Invalid pixel VM gate target or source selection')
    if (any(not re.fullmatch(r'unit_[A-Za-z][A-Za-z0-9_]*', value) for value in bindings) or
            any(name not in ABI for name in names) or len(set(names)) != len(names)):
        raise ValueError('Invalid pixel VM gate binding')
    binding = 'pixel_vm_' + target
    source = ('join([pixel_vm_parser, "\\n", ' + INPUT_NAME + ', "\\nvar pixelSources = ", text(['
              + ', '.join(bindings) + ']), ";\\n"], "")')
    prefix = 'pixelCheck(' + json.dumps(target) + ',' + json.dumps(names, separators=(',', ':'))
    # Split full-buffer scenarios across cases so each has its own outer timeout.
    suffixes = ([',' + str(i) + ',' + str(phase) for i in range(5) for phase in (0, 1)]
                if target == 'drawPixels' else [',' + str(i) for i in range(4)]
                if target == 'assembly' else [''])
    calls = [[prefix + suffix + ')', 'true'] for suffix in suffixes]
    check = 'let ' + binding + ' = js_test(' + source + ', ' + _literal(calls) + ').'
    guard = (('assert ' + binding + '.passed because ' + binding + '.report.') if retained or target == 'assembly'
             else ('ensure ' + binding + '.passed else retry because ' + binding + '.report.'))
    return [check, guard]


def lower(source, plan, *, config, reused_ids=(), asset_root=None):
    """Add per-unit and final exact-VM gates to one generic task-card program."""
    if not isinstance(source, str) or 'given ' + INPUT_NAME in source or 'let pixel_vm_' in source:
        raise ValueError('Pixel VM lowering requires fresh generic task-card source')
    rows = {row['id']: row for row in plan['units']}
    if len(rows) != len(ABI) or set(plan['order']) != set(rows) or set(plan['assembly_order']) != set(rows):
        raise ValueError('Pixel VM checks require the complete known ABI plan')
    names = {}
    for ident, row in rows.items():
        exports = row['exports']
        if len(exports) != 1 or exports[0] not in ABI or row['binding'] != 'unit_' + exports[0]:
            raise ValueError('Pixel VM plan declaration mismatch')
        names[ident] = exports[0]
    if set(names.values()) != set(ABI):
        raise ValueError('Pixel VM plan functions are incomplete')
    retained = set(reused_ids)
    if not retained <= set(rows):
        raise ValueError('Unknown retained pixel VM unit')
    host = bootstrap(config, asset_root=asset_root)
    additions, gates = {}, {}
    for ident in plan['order']:
        row = rows[ident]; name = names[ident]
        selected = [*row['closure'], ident]
        if len(set(selected)) != len(selected) or any(key not in rows for key in selected):
            raise ValueError('Invalid pixel VM dependency closure')
        chosen_names = [names[key] for key in selected]
        if any(dep not in chosen_names for key in chosen_names for dep in DEPENDENCIES[key]):
            raise ValueError('Incomplete pixel VM dependency closure')
        marker = ('assert ' if ident in retained else 'ensure ') + 'test_' + name + '.passed '
        additions[marker] = (name, gate_lines(name, [rows[key]['binding'] for key in selected], chosen_names,
                                            retained=ident in retained), ident in retained)
    lines, found = [], set()
    for line in source.splitlines():
        if line.startswith('show spec_output as '):
            all_ids = plan['assembly_order']
            added = gate_lines('assembly', [rows[key]['binding'] for key in all_ids], [names[key] for key in all_ids], retained=True)
            gates['assembly'] = {'binding': 'pixel_vm_assembly', 'check_line': len(lines) + 1, 'guard_line': len(lines) + 2, 'retained': True}
            lines.extend(added)
        lines.append(line)
        if line.startswith('program '):
            if INPUT_NAME in found:
                raise ValueError('Multiple program headers')
            lines.append('given ' + INPUT_NAME + ': Text.')
            lines.append('let pixel_vm_parser = ' + _literal(host['parser_source']) + '.')
            found.add(INPUT_NAME)
        for marker, (name, added, kept) in additions.items():
            if line.startswith(marker):
                if name in found:
                    raise ValueError('Duplicate pixel VM unit gate')
                gates[name] = {'binding': 'pixel_vm_' + name, 'check_line': len(lines) + 1, 'guard_line': len(lines) + 2, 'retained': kept}
                lines.extend(added); found.add(name)
    if found != set(ABI) | {INPUT_NAME} or 'assembly' not in gates:
        raise ValueError('Generic pixel source is missing its expected unit/output gates')
    lowered = '\n'.join(lines) + '\n'
    if len(lowered) > S.MAX_SOURCE:
        raise ValueError('VM-gated native pixel source exceeds its source budget')
    checked = S.check(lowered, execution_profile='verified')
    if not checked['ok']:
        raise ValueError('VM-gated native pixel source: ' + checked['errors'][0]['message'])
    return {'source': lowered, 'inputs': host['inputs'], 'gates': gates, 'assets': host['assets']}
