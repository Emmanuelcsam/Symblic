#!/usr/bin/env python3
"""Local beta: run Symblic's own command-line lanes with small local models, one ledger row per trial.

What it is for
    A *trial* is one (lane, fixture, model, node): run one fixture through one Symblic lane with one small Ollama
    model pinned to one node, judge the result with code only, and append exactly one row to an append-only
    ledger. Trials are grouped into batches; a batch runs the nodes in parallel and one trial per node at a time.
    This is measured machinery: it records what happened, including every failure, with its reason and evidence.

    python3 -m symblic.bench.local_beta [--config FILE] fixtures             the fixture registry
    python3 -m symblic.bench.local_beta [--config FILE] plan  --batch NAME   the trials a batch would run
    python3 -m symblic.bench.local_beta [--config FILE] batch --batch NAME   run them
    python3 -m symblic.bench.local_beta [--config FILE] trial --lane L --fixture F --pair MODEL@NODE
    python3 -m symblic.bench.local_beta [--config FILE] report [--json]     scoreboard + failures with reasons
    python3 -m symblic.bench.local_beta [--config FILE] rejudge ID          judge an unfinished run again (new row)

Configuration, not code
    Which models may run, which nodes exist (and which are reserved or excluded), the fixtures, the batches and
    the optional monitoring commands all come from a JSON file (``--config``, $SYMBLIC_LOCAL_BETA_CONFIG, or the
    example data/local_beta/config.example.json). A *node* is an Ollama host label from SYMBLIC_OLLAMA_HOSTS
    (symblic/providers/README.md); a trial pins every model call to it as ``ollama:MODEL@NODE``.

Lanes (each runs the repository's own CLI in a fresh process group):
    1 spec      compile a spec sheet (python3 -m symblic.spec.sheets) and build it with tools/symblic run; a fixture
                may name a whole-file harness (a Node script printing one JSON verdict line)
    2 native    tools/symblic run FILE.sym --by ollama:MODEL@NODE
    3 english   tools/symblic english run FILE --by ...
    4 delegate  tools/symblic delegate run TASK.json --by ...
    5 ladder    the MICA frontier ladder (tools/scripts/symblic_frontier_ladder.py), one row per rung
    6 research  an operator-configured local research command (commands.research); skipped when none is set

Outcomes. pass: code checks only (kernel ensure/js_test, the whole-file harness, exact expected strings).
fail: a check failed. refused: the lane or the model declined. timeout: the lane's own time limit or the outer cap.
error: no verdict about the model (harness trouble, a call placed off the pinned node, an unreadable result).
skipped: never started (node hot, busy or offline, model not installed, search engine down, lane not configured).

This script never calls a model itself and never retries a trial on its own: a repeat is a new row with the next
attempt number. Importing this module does nothing (the configuration is read on first use).

Depends on: tools/symblic (the Symblic CLI), symblic.spec.sheets, symblic.providers.applicators (the default
inventory of configured Ollama hosts) and symblic.bench.code_pins. Docs: docs/reference/LOCAL-BETA.md.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

VERSION = 1
SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parents[2]                      # the repository root (the folder that holds the symblic package)
BIN = REPO / 'tools' / 'symblic'              # the Symblic command line
LADDER_PY = REPO / 'tools' / 'scripts' / 'symblic_frontier_ladder.py'
DEFAULT_CONFIG = SCRIPT.parent / 'data' / 'local_beta' / 'config.example.json'
DEFAULT_STATE = Path.home() / '.local' / 'state' / 'symblic-local-beta'

LANES = {'spec': 1, 'native': 2, 'english': 3, 'delegate': 4, 'ladder': 5, 'research': 6}
VERDICTS = ('pass', 'fail', 'refused', 'timeout', 'error')     # a trial that started
OUTCOMES = VERDICTS + ('skipped',)
OLLAMA_LIMITS = {'num_predict': 2048, 'timeout_seconds': 900}  # docs/reference/SPEC-SHEETS.md (small local models)
REASON_CHARS = 300
HOT_C = 80.0                                  # default; the configuration's hot_celsius overrides it
TRIAL_OPTIONS = ('samples', 'retries', 'rounds', 'total_seconds', 'wall_seconds', 'max_calls', 'tools')
# the code a row's result depends on; hashed at trial start and end so a before/after is attributable
CODE_FILES = ('symblic/bench/local_beta.py', 'symblic/js/normalize.py', 'symblic/js/normalize.js',
              'symblic/kernel/run.py', 'symblic/kernel/language.py', 'symblic/spec/sheets.py', 'symblic/js/check.py',
              'symblic/providers/applicators.py')
# the code hashes the report prints next to a spec build
REPORTED_CODE = ('symblic/bench/local_beta.py', 'symblic/js/normalize.py', 'symblic/kernel/run.py')


class PolicyError(ValueError):
    """A trial or batch the configuration does not allow, refused before anything starts."""


# ------------------------------------------------------------------ configuration

_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z')
_COMMANDS = ('vitals', 'active_runs', 'cancel_run', 'inventory', 'research')
_CONFIG_KEYS = {'version', 'about', 'models', 'nodes', 'reserved_nodes', 'excluded_nodes', 'hot_celsius', 'commands',
                'search_health_url', 'fixtures', 'batches'}


class Config:
    """A validated local-beta configuration (see data/local_beta/config.example.json).

    models          the bare Ollama model names a trial may use (':latest' is implied)
    nodes           the node labels a trial may use; each is an Ollama host label from SYMBLIC_OLLAMA_HOSTS
    reserved_nodes  usable only with --allow-reserved (for example a machine someone else is using today)
    excluded_nodes  never used, even when named
    hot_celsius     a node reading above this temperature is skipped (only when a vitals command is configured)
    commands        optional argv lists (never run through a shell); an element may contain {node}, {id}, {model},
                    {tools} or {question} (write {{ and }} for literal braces):
                      vitals       prints {"online": bool, "temp": number or null} for {node}
                      active_runs  prints [{"id", "node", "kind", "model", "started"}] of model runs now active
                      cancel_run   cancels the run {id}; exit status 0 means cancelled
                      inventory    prints "NODE MODEL" lines (default: ask every configured Ollama host)
                      research     the lane-6 research tool; must print [{"answer", "node", "steps", ...}]
    fixtures        {name: {lane, path or question, expect...}}; paths are relative to the config file
                    (or '@repo/...' for repository paths)
    batches         {name: {"pairs": [MODEL@NODE], "trials": [[lane, fixture]]}} or {"items": [[lane, fixture,
                    MODEL@NODE, {options}]]}
    """

    def __init__(self, data, origin):
        if type(data) is not dict or type(data.get('version')) is not int or data['version'] != 1 or set(data) - _CONFIG_KEYS:
            raise PolicyError(f'{origin}: not a version 1 local-beta configuration (unknown or missing keys)')
        self.origin = Path(origin)
        self.models = tuple(self._names(data.get('models'), 'models'))
        self.nodes = tuple(self._names(data.get('nodes'), 'nodes'))
        self.reserved_nodes = tuple(self._names(data.get('reserved_nodes', []), 'reserved_nodes', empty=True))
        self.excluded_nodes = tuple(self._names(data.get('excluded_nodes', []), 'excluded_nodes', empty=True))
        hot = data.get('hot_celsius', HOT_C)
        if type(hot) not in (int, float) or not 0 < hot < 150:
            raise PolicyError(f'{origin}: hot_celsius must be a temperature in degrees Celsius')
        self.hot_c = float(hot)
        commands = data.get('commands') or {}
        if type(commands) is not dict or set(commands) - set(_COMMANDS):
            raise PolicyError(f'{origin}: commands may name only {", ".join(_COMMANDS)}')
        self.commands = {}
        for key, argv in commands.items():
            if argv is None:
                continue
            if type(argv) is not list or not argv or not all(type(a) is str and a for a in argv):
                raise PolicyError(f'{origin}: commands.{key} must be a non-empty argv list of strings (or null)')
            self.commands[key] = list(argv)
        url = data.get('search_health_url')
        if url is not None and (type(url) is not str or not re.match(r'https?://', url)):
            raise PolicyError(f'{origin}: search_health_url must be an http(s) URL or null')
        self.search_health_url = url
        self.fixtures = {}
        for name, fx in (data.get('fixtures') or {}).items():
            if type(fx) is not dict or fx.get('lane') not in LANES or not _NAME.fullmatch(str(name)):
                raise PolicyError(f'{origin}: fixture {name!r} needs a known lane')
            fx = dict(fx)
            for key in ('path', 'harness'):
                if key in fx:
                    fx[key] = self.resolve(fx[key])
            self.fixtures[name] = fx
        self.batches = {}
        for name, spec in (data.get('batches') or {}).items():
            if type(spec) is not dict or not ({'pairs', 'trials'} == set(spec) or {'items'} == set(spec)):
                raise PolicyError(f'{origin}: batch {name!r} needs pairs and trials, or items')
            self.batches[name] = spec

    def _names(self, values, key, empty=False):
        if type(values) is not list or (not values and not empty) or not all(
                type(v) is str and _NAME.fullmatch(v) for v in values) or len(set(values)) != len(values):
            raise PolicyError(f'{self.origin}: {key} must be a list of distinct plain names')
        return values

    def resolve(self, path):
        """A fixture path: absolute, ~/..., @repo/... (the repository root) or relative to the config file."""
        text = str(path)
        if text.startswith('@repo/'):
            return REPO / text[len('@repo/'):]
        candidate = Path(text).expanduser()
        return candidate if candidate.is_absolute() else self.origin.parent / candidate

    def has(self, key):
        """Is the optional command `key` configured?"""
        return key in self.commands

    def argv(self, key, **values):
        """The configured command `key` with its {placeholders} filled in, or None when it is not configured."""
        argv = self.commands.get(key)
        if argv is None:
            return None
        try:
            return [part.format(**values) for part in argv]
        except (KeyError, IndexError, ValueError) as exc:
            raise PolicyError(f'commands.{key}: cannot fill in its placeholders ({type(exc).__name__}: {exc})') from None


_CONFIG = {'config': None}


def load_config(path=None):
    """Read and validate a configuration file (default: $SYMBLIC_LOCAL_BETA_CONFIG, then the shipped example)."""
    path = Path(path or os.environ.get('SYMBLIC_LOCAL_BETA_CONFIG') or DEFAULT_CONFIG).expanduser()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise PolicyError(f'{path}: unreadable configuration ({type(exc).__name__})') from None
    return Config(data, path.resolve())


def config():
    """The active configuration (loaded on first use; use_config replaces it)."""
    if _CONFIG['config'] is None:
        _CONFIG['config'] = load_config()
    return _CONFIG['config']


def use_config(cfg):
    """Make `cfg` (a Config, a path, or None for the default) the active configuration; returns it."""
    _CONFIG['config'] = cfg if isinstance(cfg, Config) else load_config(cfg)
    return _CONFIG['config']


# ------------------------------------------------------------------ policy (pure)

def parse_pair(text):
    """'qwen3:4b-instruct@node-a' -> (model, node). The model is a bare Ollama name, never an applicator kind."""
    model, sep, node = str(text).strip().rpartition('@')
    if not sep or not model or not node:
        raise PolicyError(f'{text!r}: give MODEL@NODE, e.g. qwen3:4b-instruct@node-a')
    if model.startswith(('ollama:', 'command:', 'fake', 'claude', 'codex', 'gemini', 'chatgpt', 'agy', 'council')):
        raise PolicyError(f'{text!r}: name the Ollama model only (light local models; no cloud or CLI agent)')
    return model, node


def check_policy(model, node, allow_reserved=False, cfg=None):
    """Refuse a model or node the configuration does not allow; return (model, node)."""
    cfg = cfg or config()
    base = model[:-len(':latest')] if model.endswith(':latest') else model
    if base not in cfg.models:
        raise PolicyError(f'{model}: not one of the configured models ({", ".join(cfg.models)})')
    if node in cfg.excluded_nodes:
        raise PolicyError(f'{node}: excluded by the configuration; never used')
    if node in cfg.reserved_nodes and not allow_reserved:
        raise PolicyError(f'{node}: reserved by the configuration; pass --allow-reserved only when it is free')
    if node not in cfg.nodes and node not in cfg.reserved_nodes:
        raise PolicyError(f'{node}: not one of the configured nodes ({", ".join(cfg.nodes)})')
    return model, node


def applicator(model, node):
    """The applicator spec a trial pins: ollama:MODEL@NODE."""
    return f'ollama:{model}@{node}'


def slug(text):
    """A file-name-safe lower-case form of `text`."""
    return re.sub(r'[^a-z0-9.]+', '-', str(text).lower()).strip('-')


# ------------------------------------------------------------------ small helpers (pure)

def one_line(text, limit=REASON_CHARS):
    """Collapse whitespace and cut to `limit` characters (with an ellipsis)."""
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text if len(text) <= limit else text[:limit - 1] + '…'


def read_json_text(text):
    """The JSON document a CLI printed on stdout (its last top-level document when several)."""
    text = (text or '').strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    for start in [m.start() for m in re.finditer(r'(?m)^[{\[]', text)][::-1]:
        try:
            return json.loads(text[start:])
        except ValueError:
            continue
    return None


def read_jsonl(path):
    """The rows of a JSON-lines file ({"unreadable": True} for a bad line); None when the file is missing."""
    rows = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        rows.append({'unreadable': True})
    except FileNotFoundError:
        return None
    return rows


def sha256_file(path):
    """SHA-256 of a file, or None when it cannot be read."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def code_hashes(root=None):
    """{repository path: sha256} of CODE_FILES (None for a missing file)."""
    root = Path(root or REPO)
    return {name: sha256_file(root / name) for name in CODE_FILES}


def first_failure(error):
    """The first failing example of a js_test report: {'call','expected','got'}, or the error's first real line."""
    lines = [ln.rstrip() for ln in str(error or '').splitlines()]
    for i, ln in enumerate(lines):
        if ln.startswith('- '):
            out = {'call': ln[2:].strip()}
            for nxt in lines[i + 1:i + 4]:
                m = re.match(r'\s*(expected|got)\s+(.*)$', nxt)
                if m:
                    out[m.group(1)] = m.group(2)
            return out
    body = [ln for ln in lines if ln.strip() and not ln.startswith('failed encoded predicate')]
    return {'error': one_line(body[0] if body else error, 240)}


def spec_units(run_dir, report):
    """Per unit: calls, sampling temperatures, byte-identical replies, accepted; and the unit the build stopped at,
    with its last attempt's first failing example and the head of the model's last reply."""
    run_dir = Path(run_dir)
    calls = [c for c in (read_jsonl(run_dir / 'calls.jsonl') or []) if not c.get('unreadable')]
    trace = [t for t in (read_jsonl(run_dir / 'trace.jsonl') or []) if not t.get('unreadable')]
    accepted = {str(b.get('name')) for b in (report or {}).get('bindings') or [] if isinstance(b, dict)}
    names, units, base = {}, {}, {}
    for c in sorted(calls, key=lambda c: (c.get('sample') if isinstance(c.get('sample'), int) else 0)):
        sample = c.get('sample') if isinstance(c.get('sample'), int) and not isinstance(c.get('sample'), bool) else 0
        reply = c.get('reply') if isinstance(c.get('reply'), dict) else {}
        det = ((reply.get('meta') or {}).get('determinism') or {}) if isinstance(reply.get('meta'), dict) else {}
        if sample < 1000:                                           # each candidate's first attempt
            base[(str(c.get('stmt')), sample % 1000)] = (det.get('temperature'), det.get('seed'))
    for c in calls:
        name = str(c.get('stmt') or '')
        if not name.startswith('unit_'):
            continue
        names[str(c.get('line'))] = name
        u = units.setdefault(name, {'unit': name, 'calls': 0, 'temps': [], 'identical': 0, 'replies': [],
                                    'retries': 0, 'resampled_retries': 0})
        u['calls'] += 1
        reply = c.get('reply') if isinstance(c.get('reply'), dict) else {}
        det = ((reply.get('meta') or {}).get('determinism') or {}) if isinstance(reply.get('meta'), dict) else {}
        temp = det.get('temperature')
        if temp is not None:
            u['temps'].append(temp)
        # the sample index encodes the attempt: candidate + 100 * round + 1000 * retry (the search route of symblic.kernel.run)
        sample = c.get('sample') if isinstance(c.get('sample'), int) and not isinstance(c.get('sample'), bool) else 0
        if c.get('repair') or sample >= 1000:
            u['retries'] += 1
            # re-sampled: another temperature or seed than the candidate's first attempt (the kernel's retry rule)
            first = base.get((name, sample % 1000))
            u['resampled_retries'] += bool(first is not None and (temp, det.get('seed')) != first)
        text = reply.get('text')
        if isinstance(text, str):
            if text in u['replies']:
                u['identical'] += 1
            u['replies'].append(text)
    per_unit = []
    for name, u in units.items():
        per_unit.append({'unit': name, 'calls': u['calls'], 'retries': u['retries'],
                         'resampled_retries': u['resampled_retries'], 'temps': u['temps'], 'identical': u['identical'],
                         'accepted': name in accepted})
    failed = None
    error = (report or {}).get('error') if isinstance((report or {}).get('error'), dict) else None
    program = (run_dir / 'program.sym').read_text(encoding='utf-8', errors='replace').splitlines() \
        if (run_dir / 'program.sym').exists() else []
    stopped_line = error.get('line') if error else None
    if stopped_line and not any(t.get('kind') == 'ask' and t.get('status') == 'failed' for t in trace):
        # the build stopped outside an ask (e.g. an inconclusive js_test): name the unit that line checks
        try:
            text = program[int(stopped_line) - 1]
        except (ValueError, IndexError):
            text = ''
        m = re.match(r'\s*(?:let test_(\w+)\s*=|ensure test_(\w+)\.|ask unit_(\w+):)', text)
        if m:
            name = 'unit_' + next(g for g in m.groups() if g)
            u = units.get(name, {})
            replies = u.get('replies') or []
            failed = {'unit': name, 'line': stopped_line, 'calls': u.get('calls'), 'temps': u.get('temps'),
                      'first_failing_example': first_failure(error.get('message')),
                      'reply_head': replies[-1][:200] if replies else None}
    for t in trace:
        if failed is None and t.get('kind') == 'ask' and t.get('status') == 'failed':
            line = str(t.get('line'))
            name = names.get(line)
            attempts = [r for r in trace if r.get('kind') == 'route-attempt' and str(r.get('line')) == line]
            error = ((attempts[-1].get('ask') or {}).get('attempt') or {}).get('error') if attempts else None
            replies = units.get(name, {}).get('replies') or []
            failed = {'unit': name, 'line': t.get('line'), 'calls': units.get(name, {}).get('calls'),
                      'temps': units.get(name, {}).get('temps'), 'first_failing_example': first_failure(error),
                      'reply_head': replies[-1][:200] if replies else None}
            break
    kernel = next((t.get('kernel') for t in trace if isinstance(t.get('kernel'), dict)), None) or {}
    return per_unit, failed, kernel.get('js_normalize_assets')


def call_stats(calls, node):
    """calls.jsonl rows -> counts and placement. Every call must have run on the pinned node."""
    if calls is None:
        return {'calls': None}
    nodes, ms, ok, digests, gen_ms = set(), 0, 0, set(), 0
    for c in calls:
        reply = c.get('reply') if isinstance(c.get('reply'), dict) else {}
        where = reply.get('node')
        if not where:
            app = str(c.get('app') or '')
            where = app.rpartition('@')[2] if '@' in app else None
        if where:
            nodes.add(str(where))
        ms += int(c.get('ms') or 0)
        usage = c.get('usage') if isinstance(c.get('usage'), dict) else {}
        gen_ms += int(usage.get('duration_ms') or 0)
        ok += bool(c.get('ok'))
        ident = c.get('model_identity_raw') if isinstance(c.get('model_identity_raw'), dict) else {}
        if ident.get('digest'):
            digests.add(ident['digest'])
    off = sorted(n for n in nodes if n != node)
    # model_seconds: the sum of each call's latency as the applicator measured it, INCLUDING time spent waiting
    # for the node's model slot (parallel votes/candidates queue there). ollama_seconds: Ollama's own
    # reported duration (load + prompt + generation) summed over the calls that report it.
    return {'calls': len(calls), 'calls_ok': ok, 'call_nodes': sorted(nodes), 'placement_ok': not off,
            'off_node': off, 'model_seconds': round(ms / 1000, 1), 'ollama_seconds': round(gen_ms / 1000, 1),
            'digests': sorted(digests)}


_TIMEOUT_RE = re.compile(r'did not answer in time|time budget|stalled past|timed? ?out|deadline', re.I)
_REFUSAL_RE = re.compile(r'\brefus|\bfence[ds]?\b|not admitted|no node has|is not an available applicator|'
                         r'has no applicator in this package', re.I)
_MODEL_REFUSAL_RE = re.compile(r"^\s*(I'?m sorry|I am sorry|I cannot|I can'?t|I won'?t|As an AI)", re.I)


def classify_error(error, extra=''):
    """A failed Symblic run's error -> (outcome, reason). Timeouts and refusals keep their own names."""
    if isinstance(error, dict):
        kind = str(error.get('kind') or error.get('code') or '')
        message = str(error.get('message') or '')
        line = error.get('line')
    else:
        kind, message, line = '', str(error or ''), None
    text = message or extra or 'failed with no error message'
    head = text.strip().splitlines()[0] if text.strip() else text   # examples and replies follow on later lines
    where = f'line {line}: ' if line not in (None, 0, '0', '') else ''
    if re.search(r'\binconclusive\b|no candidate verdict', head, re.I):
        # the kernel could not finish checking a candidate (e.g. its JS sandbox ran past its wall clock on a loaded
        # host): it says so itself and gives no verdict, so the row is no verdict about the model either
        return 'error', one_line('no verdict: ' + where + text)
    if (kind == 'budget' and re.search(r'time', head, re.I)) or _TIMEOUT_RE.search(head):
        return 'timeout', one_line(where + text)
    if kind in ('version', 'contract', 'model_identity', 'refused', 'policy') or _REFUSAL_RE.search(head):
        return 'refused', one_line(where + text)
    return 'fail', one_line(where + text)


def check_outputs(outputs, expect):
    """{label or binding: exact text} against a run's outputs. -> (ok, reason, seen)."""
    seen = {}
    for o in outputs or []:
        key = o.get('label') or o.get('binding')
        if key and key not in seen:
            seen[key] = str(o.get('text'))
    for key, want in (expect or {}).items():
        if key not in seen:
            return False, one_line(f'expected output "{key}" = {want}, but the run showed no such output'), seen
        if seen[key] != want:
            return False, one_line(f'expected output "{key}" = {want}, got {seen[key]}'), seen
    return True, None, seen


def dig(value, path):
    """Follow `path` (keys and list indexes) into `value`; returns (value, found)."""
    for key in path:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and isinstance(key, int) and -len(value) <= key < len(value):
            value = value[key]
        else:
            return None, False
    return value, True


def norm_text(text):
    """Whitespace-collapsed, case-folded text for lenient string comparison."""
    return re.sub(r'\s+', ' ', str(text or '')).strip().casefold()


# ------------------------------------------------------------------ lane judges (pure: files in, verdict out)

def judge_symblic_report(report, expect=None, model_calls=None):
    """A `tools/symblic run|english run --json` report -> (outcome, reason, checks)."""
    if not isinstance(report, dict):
        return 'error', 'the lane printed no readable JSON report', {}
    status = report.get('status')
    checks = {'status': status, 'asks': report.get('asks'), 'report_calls': report.get('calls'),
              'cached': report.get('cached'), 'fingerprint': report.get('fingerprint')}
    if report.get('ok') is False and status is None:       # english CLI refusal before any run
        outcome, reason = classify_error(report.get('error'))
        return ('refused' if outcome == 'fail' else outcome), reason, checks
    if status == 'done':
        if model_calls is not None and report.get('calls') != model_calls:
            checks['model_calls_expected'] = model_calls
        ok, reason, seen = check_outputs(report.get('outputs'), expect)
        checks['expected'] = {'want': expect or {}, 'seen': {k: seen.get(k) for k in (expect or {})}}
        return ('pass', None, checks) if ok else ('fail', reason, checks)
    outcome, reason = classify_error(report.get('error'))
    return outcome, reason, checks


def harness_verdict(stdout_text, returncode):
    """A whole-file harness's last stdout line -> (ok, summary dict).

    The harness prints one JSON object: {"ok", "cases", "pass", "fail", "errors", optional "plain"/"plainOf",
    "fingerprint", "sample"}. It passes only when every case passed, nothing errored and the exit status is 0."""
    lines = [ln for ln in (stdout_text or '').strip().splitlines() if ln.strip()]
    try:
        h = json.loads(lines[-1])
    except (ValueError, IndexError):
        return False, {'ok': False, 'error': one_line(stdout_text or 'no harness output', 200)}
    observed = h.get('ok') is True and returncode == 0
    ok = bool(observed and h.get('cases', 0) > 0 and h.get('pass') == h.get('cases') and h.get('fail') == 0
              and h.get('errors') == 0 and ('plainOf' not in h or h.get('plain') == h['plainOf']))
    keep = {k: h.get(k) for k in ('cases', 'pass', 'fail', 'errors', 'plain', 'plainOf', 'fingerprint', 'error')}
    keep['ok'], keep['observed'] = ok, observed
    if h.get('sample'):
        keep['first_mismatch'] = h['sample'][0]
    return ok, keep


def judge_spec(report, program_text, harness=None):
    """A spec build: kernel unit checks first, then the independent harness. -> (outcome, reason, checks)."""
    outcome, reason, checks = judge_symblic_report(report)
    m = re.search(r'^# unit \d+ of (\d+)', program_text or '', re.M)
    checks['units_total'] = int(m.group(1)) if m else None
    bindings = report.get('bindings') if isinstance(report, dict) else None
    checks['units_accepted'] = sum(1 for b in bindings or [] if isinstance(b, dict)
                                   and str(b.get('name', '')).startswith('unit_'))
    if outcome != 'pass':
        return outcome, reason, checks
    if harness is None:
        return 'error', 'the build finished but no built file reached the harness', checks
    ok, summary = harness
    checks['harness'] = summary
    if ok:
        return 'pass', None, checks
    if not summary.get('observed'):
        return 'fail', one_line('harness could not run the built page: ' + str(summary.get('error'))), checks
    first = summary.get('first_mismatch') or {}
    return 'fail', one_line(f"harness {summary.get('pass')}/{summary.get('cases')} documents, plain "
                            f"{summary.get('plain')}/{summary.get('plainOf')}; first mismatch seed {first.get('seed')}: "
                            f"want {first.get('want')!r} got {first.get('got')!r}"), checks


def judge_delegate(receipt, expect_result):
    """A `tools/symblic delegate run` receipt -> (outcome, reason, checks): accepted AND the expected value."""
    if not isinstance(receipt, dict):
        return 'error', 'the delegate run printed no readable receipt', {}
    checks = {'accepted': receipt.get('accepted'), 'status': receipt.get('status'),
              'contract_id': receipt.get('contract_id'), 'receipt_calls': receipt.get('calls')}
    if receipt.get('ok') is False and 'accepted' not in receipt:        # refused before any run
        errors = receipt.get('errors') or [{}]
        _, reason = classify_error(errors[0] if isinstance(errors[0], dict) else {'message': errors[0]})
        return 'refused', reason, checks
    if receipt.get('accepted') is not True:
        error = receipt.get('error') or (receipt.get('report') or {}).get('error')
        outcome, reason = classify_error(error)
        return outcome, reason or 'not accepted', checks
    value, found = dig(receipt.get('result'), (expect_result or {}).get('path') or [])
    want = (expect_result or {}).get('equals')
    checks['expected'] = {'path': (expect_result or {}).get('path'), 'want': want, 'got': value}
    if expect_result and (not found or value != want):
        return 'fail', one_line(f'accepted, but result {"/".join(map(str, expect_result.get("path") or [])) or "value"} '
                                f'= {value!r}, expected {want!r}'), checks
    return 'pass', None, checks


def judge_research(results, expect):
    """The research tool's JSON -> pass when the ANSWER contains the expected string (case and spacing aside)."""
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return 'error', 'the research tool printed no readable result', {}
    r = results[0]
    checks = {'node': r.get('node'), 'model': r.get('model'), 'research_seconds': r.get('seconds'),
              'tool_uses': len(r.get('steps') or []), 'sources': len(r.get('sources') or [])}
    if r.get('error'):
        outcome, reason = classify_error({'message': r['error']})
        return outcome, reason, checks
    answer = str(r.get('answer') or '')
    checks['answer_head'] = one_line(answer, 400)
    checks['expected'] = expect
    checks['exact_case'] = expect in answer
    if norm_text(expect) in norm_text(answer):
        return 'pass', None, checks
    if _MODEL_REFUSAL_RE.search(answer):
        return 'refused', one_line('model declined: ' + answer), checks
    return 'fail', one_line(f'ANSWER lacks "{expect}"; it reads: {answer}'), checks


# ------------------------------------------------------------------ the outside world (replaced by fakes in tests)

class Env:
    """Side effects: processes, the configured monitoring commands, the Ollama hosts' listings, the clock.

    Without a vitals command a node counts as online when its Ollama host lists at least one model, and its
    temperature is unknown (no heat gate). Without an active_runs command there is no busy gate; without a
    cancel_run command nothing outside the trial's own process group is cancelled."""

    def __init__(self, cfg=None):
        self.cfg = cfg or config()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def now(self):
        return time.time()

    def sleep(self, seconds):
        time.sleep(seconds)

    def monitored(self):
        """True when node temperatures come from a configured vitals command."""
        return self.cfg.has('vitals')

    def _json_command(self, key, timeout=60, **values):
        argv = self.cfg.argv(key, **values)
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=REPO)
        if out.returncode != 0:
            raise OSError(f'{key} command exited {out.returncode}')
        return json.loads(out.stdout)

    def node_vitals(self, node, force=True):
        """(online, temperature °C or None) from the vitals command, else from the node's Ollama listing."""
        if not self.monitored():
            return node in self.inventory(), None
        data = self._json_command('vitals', node=node)
        raw = data.get('temp') if isinstance(data, dict) else None
        temp = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
        online = bool(data.get('online')) if isinstance(data, dict) else False
        return online, (temp if temp is not None and math.isfinite(temp) and temp > 0 else None)

    def active_runs(self):
        """Model runs now active ([{'id', 'node', 'kind', 'model', 'started'}]); [] without an active_runs command."""
        if not self.cfg.has('active_runs'):
            return []
        rows = self._json_command('active_runs')
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

    def search_up(self):
        """Is the research lane's search engine answering? True when no health URL is configured."""
        url = self.cfg.search_health_url
        if not url:
            return True
        try:
            with self.opener.open(url, timeout=5) as r:
                return r.status == 200
        except Exception:  # noqa: BLE001
            return False

    def inventory(self):
        """{node: {model, ...}}: the inventory command's "NODE MODEL" lines, else every configured Ollama host's
        /api/tags listing (symblic.providers.applicators; a host that does not answer lists nothing)."""
        argv = self.cfg.argv('inventory')
        inv = {}
        if argv is not None:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=180, cwd=REPO)
            for line in out.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    inv.setdefault(parts[0], set()).add(parts[1])
            return inv
        from symblic.providers import applicators as providers
        for row in providers.Applicators.inventory():
            inv.setdefault(row['node'], set()).add(row['model'])
        return inv

    def cancel_run(self, run_id):
        """Cancel one model run this trial started, through the cancel_run command (False when none is set)."""
        argv = self.cfg.argv('cancel_run', id=run_id)
        if argv is None:
            return False
        p = subprocess.run(argv, capture_output=True, text=True, timeout=120, cwd=REPO)
        return p.returncode == 0

    def run(self, argv, *, cwd, env, stdout_path, stderr_path, timeout, grace=60):
        """Run one lane command in its own process group; past `timeout`, SIGTERM (the lanes cancel their own
        calls on it), then SIGKILL after `grace`."""
        t0 = time.monotonic()
        with open(stdout_path, 'wb') as out, open(stderr_path, 'wb') as err:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                    start_new_session=True)
            timed_out = False
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    code = proc.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    code = proc.wait()
                except ProcessLookupError:
                    code = proc.wait()
        return {'exit': code, 'timed_out': timed_out, 'seconds': round(time.monotonic() - t0, 1)}


def node_binary():
    """The Node.js binary the kernel uses (symblic.js.check): $SYMBLIC_NODE, the newest nvm install, then PATH."""
    import glob
    import shutil
    found = os.environ.get('SYMBLIC_NODE')
    if not found:
        versions = sorted(glob.glob(os.path.expanduser('~/.nvm/versions/node/v*/bin/node')),
                          key=lambda p: [int(x) for x in re.findall(r'\d+', p.split('/v')[-1])[:3]])
        found = versions[-1] if versions else (shutil.which('node') or 'node')
    return found


# ------------------------------------------------------------------ ledger

class Ledger:
    """The append-only JSON-lines ledger: one row per trial, written with an exclusive lock and fsync."""
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def rows(self):
        """Every readable row."""
        return [r for r in (read_jsonl(self.path) or []) if not r.get('unreadable')]

    def next_attempt(self, lane, fixture, model, node):
        """The attempt number the next trial of this (lane, fixture, model, node) gets."""
        with self._lock:
            return 1 + sum(1 for r in self.rows() if not r.get('supersedes')
                           and (r.get('lane'), r.get('fixture'), r.get('model'), r.get('node')) == (lane, fixture, model, node))

    def append(self, row):
        """Append one row (durable before returning)."""
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        line = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + '\n'
        with self._lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, line.encode('utf-8'))
                os.fsync(fd)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        return row


def effective(rows):
    """The rows a scoreboard counts: a rejudged row replaces the row it supersedes (both stay in the ledger)."""
    replaced = {r['supersedes'] for r in rows if r.get('supersedes')}
    return [r for r in rows if r.get('id') not in replaced or r.get('supersedes')]


def rejudge(row):
    """A row whose run did not finish, judged again from its saved lane output with the current judges."""
    if row.get('lane') not in ('spec', 'native', 'english') or not row.get('evidence'):
        raise PolicyError('rejudge covers spec, native and english rows with an evidence folder')
    folder = Path(row['evidence'])
    report = read_json_text(Trial._text(folder / 'lane.out'))
    if not isinstance(report, dict) or report.get('status') == 'done':
        raise PolicyError('that run finished (or its report is unreadable): judging it again would repeat the expected '
                          'checks or the harness; run the trial again instead (a new row)')
    if row['lane'] == 'spec':
        outcome, reason, checks = judge_spec(report, Trial._text(folder / 'build.sym'), None)
        per_unit, failed, assets = spec_units(folder / 'run', report)
        checks['per_unit'] = per_unit
        if failed:
            checks['failed_unit'] = failed
        if assets:
            checks['kernel_js_normalize_assets'] = assets
    else:
        outcome, reason, checks = judge_symblic_report(report)
    return {**row, 'id': row['id'] + '-rejudged', 'supersedes': row['id'], 'outcome': outcome, 'reason': reason,
            'checks': {**(row.get('checks') or {}), **checks}, 'rejudged': iso(time.time()),
            'rejudge_tool': (sha256_file(SCRIPT) or '')[:16], 'was': {'outcome': row.get('outcome'), 'reason': row.get('reason')}}


def iso(ts):
    """Local ISO-8601 time with offset for a POSIX timestamp."""
    return time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(ts))


# ------------------------------------------------------------------ one trial

class Trial:
    """One (lane, fixture, model, node) run through the lane's own CLI, judged by code, written as one row."""

    def __init__(self, lane, fixture, model, node, *, state, env, ledger, batch='adhoc', allow_reserved=False,
                 hot_c=None, hot_wait=600, busy_wait=900, poll=30, log=None, approve_over_hour=False, options=None,
                 batch_name=None, cfg=None):
        self.cfg = cfg = cfg or config()
        if fixture not in cfg.fixtures or cfg.fixtures[fixture]['lane'] != lane:
            raise PolicyError(f'{fixture}: not a {lane} fixture (see `fixtures`)')
        check_policy(model, node, allow_reserved, cfg)
        unknown = set(options or {}) - set(TRIAL_OPTIONS)
        if unknown:
            raise PolicyError(f'unknown trial options {sorted(unknown)}')
        self.lane, self.fixture, self.model, self.node = lane, fixture, model, node
        self.fx = {**cfg.fixtures[fixture], **(options or {})}
        self.options = dict(options or {})
        self.batch_name = batch_name
        self.state, self.env, self.ledger, self.batch = Path(state), env, ledger, batch
        self.hot_c = cfg.hot_c if hot_c is None else hot_c
        self.hot_wait, self.busy_wait, self.poll = hot_wait, busy_wait, poll
        self.log = log or (lambda msg: None)
        self.approve_over_hour = approve_over_hour
        self.app = applicator(model, node)
        self.tool = (sha256_file(SCRIPT) or '')[:16]     # which version of this script wrote the row

    # -- gates before a trial starts
    def _gate(self):
        """(None, temperature) when the node is online, cool and free; else (the reason to skip, temperature).
        Temperature is checked only when a vitals command is configured (Env.monitored)."""
        waited = 0
        while True:
            try:
                online, temp = self.env.node_vitals(self.node, force=True)
            except Exception as e:  # noqa: BLE001
                return f'node status unreadable ({type(e).__name__}); temperature unknown', None
            if not online:
                return f'{self.node} is offline', temp
            busy = []
            try:
                busy = [r for r in self.env.active_runs() if r.get('node') == self.node
                        and (r.get('kind') or r.get('agent_kind')) in ('ollama', 'llamacpp')]
            except Exception as e:  # noqa: BLE001
                return f'active runs unreadable ({type(e).__name__})', temp
            if temp is None and self.env.monitored():
                return f'{self.node} temperature unreadable', None
            hot = temp is not None and temp > self.hot_c
            if not hot and not busy:
                return None, temp
            limit = self.hot_wait if hot else self.busy_wait
            if waited >= limit:
                if hot:
                    return f'{self.node} at {temp:.0f} °C, above {self.hot_c:.0f} °C after {waited} s', temp
                return (f'{self.node} busy with another model run ({busy[0].get("model")}, {busy[0].get("id")}) '
                        f'after {waited} s'), temp
            self.log(f'{self.node}: waiting ({"hot %.0f °C" % temp if hot else "busy"})')
            self.env.sleep(self.poll)
            waited += self.poll

    def _row(self, attempt, started, **fields):
        row = {'v': VERSION, 'batch': self.batch, 'lane': self.lane, 'lane_no': LANES[self.lane],
               'fixture': self.fixture, 'fixture_path': str(self.fx.get('path') or ''),
               'fixture_sha256': sha256_file(self.fx['path']) if self.fx.get('path') else None,
               'model': self.model, 'node': self.node, 'applicator': self.app, 'attempt': attempt, 'tool': self.tool,
               'started': iso(started), 'started_ts': round(started, 3)}
        if self.batch_name:
            row['batch_name'] = self.batch_name
        if self.options:
            row['options'] = self.options
        row.update(fields)
        return row

    def run(self):
        """Gate, run the lane, judge, and append exactly one row (or one per ladder rung); returns it."""
        attempt = self.ledger.next_attempt(self.lane, self.fixture, self.model, self.node)
        tid = f'{self.batch}-{self.lane}-{self.fixture}-{slug(self.model)}-{self.node}-a{attempt}'
        queued = self.env.now()
        skip, temp = None, None
        if self.lane == 'research' and not self.cfg.has('research'):
            skip = 'no research command is configured (commands.research)'
        if skip is None:
            skip, temp = self._gate()
        if skip is None and self.lane == 'research' and not self.env.search_up():
            skip = f'search engine {self.cfg.search_health_url} is down'
        if skip is not None:
            ended = self.env.now()
            return self.ledger.append(self._row(attempt, queued, id=tid, ended=iso(ended), ended_ts=round(ended, 3),
                                                seconds=round(ended - queued, 1), waited_seconds=round(ended - queued, 1),
                                                outcome='skipped', reason=skip, temp_before=temp, calls=None,
                                                evidence=None))
        started = self.env.now()           # the trial's own clock starts after the gate; the wait is kept apart
        code_before = code_hashes()
        folder = self.state / 'runs' / tid
        n = 1
        while folder.exists():           # an interrupted trial left its folder and no row; never reuse a record
            n += 1
            folder = self.state / 'runs' / f'{tid}-r{n}'
        tid = folder.name
        folder.mkdir(parents=True, mode=0o700)
        (folder / 'intent.json').write_text(json.dumps(self._row(attempt, started, id=tid, temp_before=temp,
                                                                 pid=os.getpid()), default=str) + '\n')
        self.log(f'start {tid} ({temp} °C)')
        heat = {'max': temp}
        stop = threading.Event()

        def watch():
            while not stop.wait(60):
                try:
                    _, t = self.env.node_vitals(self.node, force=False)
                    if t is not None:
                        heat['max'] = max(heat['max'] or t, t)
                except Exception:  # noqa: BLE001
                    pass
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            result = getattr(self, '_lane_' + self.lane)(folder)
        except Exception as e:  # noqa: BLE001  (the tool failed, not the model)
            result = {'outcome': 'error', 'reason': one_line(f'beta harness: {type(e).__name__}: {e}')}
        finally:
            stop.set()
        ended = self.env.now()
        cancelled = []
        if result.pop('killed', False):
            cancelled = self._cancel_leftovers(started)
        rows = result.pop('rows', None)
        code_after = code_hashes()
        common = dict(ended=iso(ended), ended_ts=round(ended, 3), seconds=round(ended - started, 1),
                      waited_seconds=round(started - queued, 1), temp_before=temp, temp_max=heat['max'],
                      evidence=str(folder), runner_load1=_load1(), cancelled_runs=cancelled,
                      code_sha256=code_before,
                      code_changed_during_trial=sorted(k for k in code_before if code_before[k] != code_after.get(k)))
        if rows:          # the ladder writes one row per rung
            return [self.ledger.append(self._row(attempt, started, id=f'{tid}-{r.pop("rung_mode")}', **common, **r))
                    for r in rows]
        stats = result.pop('stats', None) or {'calls': None}
        if stats.get('calls') is not None and stats.get('placement_ok') is False and result['outcome'] != 'skipped':
            result['reason'] = one_line(f'placement: calls ran on {", ".join(stats["off_node"])}, not {self.node}; '
                                        f'was {result["outcome"]}: {result.get("reason") or ""}')
            result['outcome'] = 'error'
        if self.fx.get('model_calls') == 0 and stats.get('calls'):
            result.setdefault('checks', {})['note'] = 'a kernel-only fixture made model calls'
        row = self._row(attempt, started, id=tid, **common, **stats, **result)
        self.log(f'end {tid}: {row["outcome"]}' + (f' ({row.get("reason")})' if row.get('reason') else ''))
        return self.ledger.append(row)

    def _cancel_leftovers(self, since):
        """After a killed lane command: cancel its runs still holding this node (started during the trial)."""
        done = []
        try:
            for r in self.env.active_runs():
                if (r.get('node') == self.node and (r.get('kind') or r.get('agent_kind')) == 'ollama'
                        and str(r.get('model') or '').split(':latest')[0] == self.model.split(':latest')[0]
                        and float(r.get('started') or 0) >= since - 5):
                    if self.env.cancel_run(r['id']):
                        done.append(r['id'])
        except Exception as e:  # noqa: BLE001
            done.append(f'cancel check failed: {type(e).__name__}')
        return done

    def _env(self):
        """The lane process environment: the caller's, with this repository importable."""
        env = dict(os.environ)
        env['PYTHONPATH'] = str(REPO) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        return env

    def _exec(self, folder, argv, timeout, name='lane'):
        (folder / f'{name}.cmd').write_text(shlex.join(argv) + '\n')
        return self.env.run(argv, cwd=str(REPO), env=self._env(), stdout_path=folder / f'{name}.out',
                            stderr_path=folder / f'{name}.err', timeout=timeout)

    @staticmethod
    def _text(path):
        try:
            return Path(path).read_text(encoding='utf-8', errors='replace')
        except OSError:
            return ''

    def _why_unreadable(self, folder, res, reason):
        """An unreadable lane result: add the exit code and the last stderr line, so the row says what broke."""
        tail = [ln for ln in self._text(folder / 'lane.err').splitlines() if ln.strip()][-1:]
        return one_line(f'{reason} (exit {res["exit"]}' + (f'; stderr: {tail[0]}' if tail else '') + ')')

    def _timed_out(self, res, cap, what):
        return {'outcome': 'timeout', 'reason': f'{what} passed the outer cap of {cap} s and was stopped',
                'exit': res['exit'], 'killed': True}

    # -- lane 1: spec sheet -> compile -> tools/symblic run -> harness
    def _lane_spec(self, folder):
        fx = self.fx
        build = folder / 'build.sym'
        cargv = [sys.executable, '-m', 'symblic.spec.sheets', 'compile', str(fx['path']), '--by', self.app,
                 '--samples', str(fx['samples']), '--retries', str(fx['retries']), '--rounds', str(fx['rounds'])]
        cres = self._exec(folder, cargv, 300, name='compile')
        if cres['exit'] != 0 or cres['timed_out']:
            return {'outcome': 'refused', 'reason': one_line('compile refused the sheet: ' + self._text(folder / 'compile.err')),
                    'exit': cres['exit']}
        program = self._text(folder / 'compile.out')
        build.write_text(program)
        named = sorted(set(re.findall(r'"((?:ollama|command|fake|claude|codex|gemini|chatgpt|agy|mistral|copilot|council)[^"]*)"',
                                      '\n'.join(re.findall(r'^use by=\[(.*?)\]', program, re.M)))))
        if named != [self.app]:          # placement guard: the program must name only the pinned applicator
            return {'outcome': 'error', 'reason': one_line(f'compiled program names {named or "no applicator"}, '
                                                           f'not only {self.app}; nothing was run')}
        limits = {**OLLAMA_LIMITS, 'total_timeout_seconds': fx['total_seconds']}
        cap = fx['total_seconds'] + 600
        argv = [str(BIN), 'run', str(build), '--dir', str(folder / 'run'), '--json', '--ollama-limits',
                json.dumps(limits, separators=(',', ':'))]
        res = self._exec(folder, argv, cap)
        stats = call_stats(read_jsonl(folder / 'run' / 'calls.jsonl'), self.node)
        if res['timed_out']:
            return {**self._timed_out(res, cap, 'the build'), 'stats': stats, 'limits': limits}
        report = read_json_text(self._text(folder / 'lane.out'))
        harness = None
        if isinstance(report, dict) and report.get('status') == 'done':
            page = next((o.get('value') or o.get('text') for o in report.get('outputs') or []
                         if o.get('label') == fx['file'] or str(o.get('label', '')).endswith('.html')), None)
            if page:
                (folder / fx['file']).write_text(page)
                hres = self.env.run([node_binary(), str(fx['harness']), str(folder / fx['file'])], cwd=str(REPO),
                                    env=self._env(), stdout_path=folder / 'harness.out',
                                    stderr_path=folder / 'harness.err', timeout=600)
                harness = harness_verdict(self._text(folder / 'harness.out'), hres['exit'])
        outcome, reason, checks = judge_spec(report, self._text(build), harness)
        if report is None:
            reason = self._why_unreadable(folder, res, reason)
        try:
            per_unit, failed, assets = spec_units(folder / 'run', report if isinstance(report, dict) else {})
            checks['per_unit'] = per_unit
            if failed:
                checks['failed_unit'] = failed
            if assets:
                checks['kernel_js_normalize_assets'] = assets   # as the run's own kernel identity recorded them
        except Exception as e:  # noqa: BLE001  (detail only; the verdict above stands)
            checks['per_unit_error'] = f'{type(e).__name__}: {e}'
        settings = {k: fx[k] for k in ('samples', 'retries', 'rounds')}
        return {'outcome': outcome, 'reason': reason, 'checks': checks, 'exit': res['exit'], 'stats': stats,
                'limits': limits, 'settings': settings}

    # -- lane 2: native .sym
    def _lane_native(self, folder):
        fx = self.fx
        limits = {**OLLAMA_LIMITS, 'total_timeout_seconds': fx['total_seconds']}
        cap = fx['total_seconds'] + 300
        argv = [str(BIN), 'run', str(fx['path']), '--by', self.app, '--dir', str(folder / 'run'), '--json',
                '--ollama-limits', json.dumps(limits, separators=(',', ':'))]
        res = self._exec(folder, argv, cap)
        stats = call_stats(read_jsonl(folder / 'run' / 'calls.jsonl'), self.node)
        if res['timed_out']:
            return {**self._timed_out(res, cap, 'the run'), 'stats': stats, 'limits': limits}
        report = read_json_text(self._text(folder / 'lane.out'))
        outcome, reason, checks = judge_symblic_report(report, fx.get('expect'), fx.get('model_calls'))
        if report is None:
            reason = self._why_unreadable(folder, res, reason)
        if stats.get('calls') is None:
            stats = {**stats, 'calls': 0 if outcome != 'error' else None}
        return {'outcome': outcome, 'reason': reason, 'checks': checks, 'exit': res['exit'], 'stats': stats,
                'limits': limits}

    # -- lane 3: English statements
    def _lane_english(self, folder):
        fx = self.fx
        cap = fx['wall_seconds']
        argv = [str(BIN), 'english', 'run', str(fx['path']), '--dir', str(folder / 'run'), '--by', self.app,
                '--max-calls', str(fx['max_calls']), '--json']
        res = self._exec(folder, argv, cap)
        stats = call_stats(read_jsonl(folder / 'run' / 'calls.jsonl'), self.node)
        if res['timed_out']:
            return {**self._timed_out(res, cap, 'the English run'), 'stats': stats}
        report = read_json_text(self._text(folder / 'lane.out'))
        outcome, reason, checks = judge_symblic_report(report, fx.get('expect'))
        if report is None:
            reason = self._why_unreadable(folder, res, reason)
        return {'outcome': outcome, 'reason': reason, 'checks': checks, 'exit': res['exit'], 'stats': stats}

    # -- lane 4: delegate templates
    def _lane_delegate(self, folder):
        fx = self.fx
        cap = fx['wall_seconds']
        argv = [str(BIN), 'delegate', 'run', str(fx['path']), '--dir', str(folder / 'run'), '--by', self.app,
                '--agent-json']
        res = self._exec(folder, argv, cap)
        stats = call_stats(read_jsonl(folder / 'run' / 'calls.jsonl'), self.node)
        if res['timed_out']:
            return {**self._timed_out(res, cap, 'the delegate run'), 'stats': stats}
        receipt = read_json_text(self._text(folder / 'lane.out'))
        outcome, reason, checks = judge_delegate(receipt, fx.get('expect_result'))
        if receipt is None:
            reason = self._why_unreadable(folder, res, reason)
        return {'outcome': outcome, 'reason': reason, 'checks': checks, 'exit': res['exit'], 'stats': stats}

    # -- lane 6: local web research
    def _lane_research(self, folder):
        fx = self.fx
        cap = fx['wall_seconds']
        model = self.model if ':' in self.model else self.model + ':latest'   # the exact Ollama tag
        argv = self.cfg.argv('research', model=model, node=self.node, tools=fx['tools'], question=fx['question'])
        res = self._exec(folder, argv, cap)
        if res['timed_out']:
            return {**self._timed_out(res, cap, 'the research run'), 'stats': {'calls': None}}
        results = read_json_text(self._text(folder / 'lane.out'))
        outcome, reason, checks = judge_research(results, fx['expect'])
        if results is None:
            reason = self._why_unreadable(folder, res, reason)
        steps = (results[0].get('steps') if isinstance(results, list) and results and isinstance(results[0], dict)
                 else None)
        answered = isinstance(results, list) and results and isinstance(results[0], dict) and 'answer' in results[0]
        calls = (len(steps or []) + 1) if answered else None
        node_seen = results[0].get('node') if isinstance(results, list) and results and isinstance(results[0], dict) else None
        stats = {'calls': calls, 'calls_source': 'tool steps + 1 answer (the research tool keeps no calls.jsonl)',
                 'call_nodes': [node_seen] if node_seen else [], 'placement_ok': node_seen in (None, self.node),
                 'off_node': [node_seen] if node_seen not in (None, self.node) else []}
        saved = re.search(r'^saved (\S+)', self._text(folder / 'lane.err'), re.M)
        if saved:
            checks['report_file'] = saved.group(1)
        return {'outcome': outcome, 'reason': reason, 'checks': checks, 'exit': res['exit'], 'stats': stats}

    # -- lane 5: the frontier ladder (MICA promote/ladder), one row per rung
    def _lane_ladder(self, folder):
        fx = self.fx
        root = self.state / 'ladder' / f'{fx["family"].lower()}-{slug(self.model)}-{self.node}-{self.batch}'
        plan_dir = Path(str(root) + '-plan')
        pargv = [sys.executable, str(LADDER_PY), 'plan', '--model', self.model, '--node', self.node, '--root', str(root),
                 '--budget-seconds', str(fx['budget_seconds']), '--max-calls', str(fx['max_calls']),
                 '--families', fx['family'], '--plan-dir', str(plan_dir), '--json']
        pres = self._exec(folder, pargv, 300, name='plan')
        plan = read_json_text(self._text(folder / 'plan.out'))
        if pres['exit'] != 0 or not isinstance(plan, dict):
            return {'outcome': 'refused', 'reason': one_line('ladder plan refused: ' + self._text(folder / 'plan.err'))}
        session = (plan.get('commands') or {}).get('run') or []
        if not session:
            return {'outcome': 'error', 'reason': 'ladder plan has no run session'}
        session = session[0]
        if session.get('over_hour_bound') and not self.approve_over_hour:
            return {'outcome': 'refused', 'reason': one_line(
                f'session estimate {session.get("estimated_seconds")} s is over the one-hour bound; the operator '
                'must approve it (--approve-over-hour). Nothing was frozen or run.')}
        mres = self._exec(folder, [sys.executable, str(LADDER_PY), 'materialize', '--plan', plan['plan_file']], 300,
                          name='materialize')
        if mres['exit'] != 0:
            return {'outcome': 'refused', 'reason': one_line('materialize refused: ' + self._text(folder / 'materialize.err'))}
        freeze = plan['commands']['freeze'][0]
        if Path(freeze['stdout']).exists():
            return {'outcome': 'refused', 'reason': f'a freeze pin already exists at {freeze["stdout"]}; never overwritten'}
        fres = self._exec(folder, freeze['argv'], 900, name='freeze')
        pin = read_json_text(self._text(folder / 'freeze.out'))
        if fres['exit'] != 0 or not isinstance(pin, dict) or pin.get('status') != 'frozen':
            return {'outcome': 'refused', 'reason': one_line('freeze failed: ' + self._text(folder / 'freeze.err'))}
        Path(freeze['stdout']).write_text(self._text(folder / 'freeze.out'))
        cap = int(session.get('runtime_max_seconds') or 3600) + 600
        rres = self._exec(folder, ['bash', '-c', session['shell']], cap, name='session')
        ares = self._exec(folder, [sys.executable, str(LADDER_PY), 'aggregate', '--plan', plan['plan_file'], '--json'],
                          600, name='aggregate')
        agg = read_json_text(self._text(folder / 'aggregate.out'))
        rows = ladder_rows(agg, session_exit=rres['exit'], timed_out=rres['timed_out'])
        if not rows:
            return {'outcome': 'error', 'reason': one_line(f'aggregate unreadable (exit {ares["exit"]}): '
                                                           + self._text(folder / 'aggregate.err')),
                    'killed': rres['timed_out']}
        return {'rows': rows, 'killed': rres['timed_out']}


def ladder_rows(agg, session_exit=None, timed_out=False):
    """Aggregate JSON -> one row per rung: pass only for the bench's own success (done, every hidden case)."""
    if not isinstance(agg, dict) or not agg.get('cells'):
        return []
    rows = []
    for c in agg['cells']:
        statuses = c.get('statuses') or {}
        if c.get('assigned') and c.get('passed') == c.get('assigned'):
            outcome, reason = 'pass', None
        elif statuses.get('blocked'):
            outcome, reason = 'refused', 'assignment blocked'
        elif timed_out:
            outcome, reason = 'timeout', 'the session passed its outer cap'
        elif any(k in statuses for k in ('unknown', 'pending', 'damaged', 'stopped', 'not_frozen', 'pin_unreadable',
                                         'unreadable')):
            outcome, reason = 'error', 'unresolved: ' + ', '.join(f'{k} {v}' for k, v in sorted(statuses.items()))
        else:
            outcome, reason = 'fail', one_line('no hidden pass: ' + ', '.join(f'{k} {v}' for k, v in sorted(statuses.items()))
                                               + '; grades ' + json.dumps(c.get('grade_statuses') or {}, sort_keys=True))
        calls = (c.get('calls') or {}).get('observed_total')
        rows.append({'rung_mode': c.get('mode'), 'fixture': f'ladder-{c.get("family")}/{c.get("rung")}-{c.get("mode")}',
                     'outcome': outcome, 'reason': reason, 'calls': calls,
                     'checks': {'rung': c.get('rung'), 'mode': c.get('mode'), 'assigned': c.get('assigned'),
                                'passed': c.get('passed'), 'statuses': statuses, 'grades': c.get('grade_statuses'),
                                'wall_seconds': c.get('wall_seconds'), 'session_exit': session_exit}})
    return rows


def _load1():
    try:
        return round(os.getloadavg()[0], 2)
    except OSError:
        return None


# ------------------------------------------------------------------ batch: one trial per node at a time

def batch_trials(name, pairs=None, cfg=None):
    """(lane, fixture, model, node, options) in run order. An item batch names its own pairs and settings."""
    cfg = cfg or config()
    if name not in cfg.batches:
        raise PolicyError(f'unknown batch {name!r} (configured: {", ".join(sorted(cfg.batches)) or "none"})')
    spec = cfg.batches[name]
    if 'items' in spec:
        if pairs:
            raise PolicyError(f'batch {name} names its own model and node per item; --pair does not apply')
        return [(lane, fixture, *parse_pair(pair), dict(options or {})) for lane, fixture, pair, options in spec['items']]
    return [(lane, fixture, *parse_pair(p), {}) for p in (pairs or spec['pairs']) for lane, fixture in spec['trials']]


def run_batch(trials, *, state, env, ledger, batch, allow_reserved=False, log=None, inventory=None, cfg=None, **kw):
    """Group by node; each node runs its trials one after another; the nodes run in parallel."""
    cfg = cfg or config()
    log = log or (lambda m: None)
    trials = [t if len(t) == 5 else (*t, {}) for t in trials]
    for lane, fixture, model, node, _ in trials:          # refuse the whole batch before anything starts
        check_policy(model, node, allow_reserved, cfg)
        if cfg.fixtures.get(fixture, {}).get('lane') != lane:
            raise PolicyError(f'{fixture}: not a {lane} fixture')
        if lane == 'ladder':
            raise PolicyError('the ladder is a separate long trial: run it with `trial --lane ladder`')
    if inventory is not None:
        inv = inventory
    else:
        try:
            inv = env.inventory()
        except Exception as e:  # noqa: BLE001  (unknown inventory: the lane itself refuses a missing model)
            log(f'inventory unreadable ({type(e).__name__}); not pre-checking installed models')
            inv = None
    by_node = {}
    for t in trials:
        by_node.setdefault(t[3], []).append(t)
    rows, lock = [], threading.Lock()

    def worker(items):
        for lane, fixture, model, node, options in items:
            have = (inv or {}).get(node) or set()
            if inv is not None and model not in have and model + ':latest' not in have:
                tr = Trial(lane, fixture, model, node, state=state, env=env, ledger=ledger, batch=batch,
                           allow_reserved=allow_reserved, log=log, options=options, cfg=cfg, **kw)
                t = env.now()
                row = ledger.append(tr._row(ledger.next_attempt(lane, fixture, model, node), t,
                                            id=f'{batch}-{lane}-{fixture}-{slug(model)}-{node}-missing',
                                            ended=iso(t), ended_ts=round(t, 3), seconds=0.0, outcome='skipped',
                                            reason=f'{model} is not installed on {node} (inventory)',
                                            calls=None, evidence=None))
            else:
                row = Trial(lane, fixture, model, node, state=state, env=env, ledger=ledger, batch=batch,
                            allow_reserved=allow_reserved, log=log, options=options, cfg=cfg, **kw).run()
            with lock:
                rows.extend(row if isinstance(row, list) else [row])

    threads = [threading.Thread(target=worker, args=(items,), name=f'beta-{node}') for node, items in by_node.items()]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return rows


# ------------------------------------------------------------------ report

def scoreboard(rows):
    """{(lane_no, lane): {model: counts}}: total counts every started trial; skipped stays outside."""
    board = {}
    for r in rows:
        key = (r.get('lane_no') or LANES.get(r.get('lane'), 0), r.get('lane'))
        cell = board.setdefault(key, {}).setdefault(r.get('model'), {o: 0 for o in OUTCOMES})
        cell[r.get('outcome') if r.get('outcome') in OUTCOMES else 'error'] += 1
    return board


def render_report(rows, ledger_path, all_rows=None, batches=None, alive=None):
    """The text scoreboard (lane x model) and every non-pass with its reason and evidence folder."""
    rows = effective(rows)
    if not rows:
        return f'No trials yet in {ledger_path}.'
    models = sorted({r.get('model') for r in rows}, key=lambda m: (-_size(m), m))
    board = scoreboard(rows)
    batches = sorted({str(r.get('batch')) for r in rows})
    out = [f'Symblic local beta: {len(rows)} rows in {ledger_path} (batches {", ".join(batches)})',
           'Cell = pass/total over trials that started; f fail, r refused, t timeout, e error; s = skipped (not in total).',
           '']
    width = max(14, *(len(m) for m in models)) + 2
    out.append(f'{"lane":<14}' + ''.join(f'{m:<{width}}' for m in models))
    for (no, lane) in sorted(board):
        line = ('%d %s' % (no, lane)).ljust(14)
        for m in models:
            c = board[(no, lane)].get(m)
            if not c:
                line += '-'.ljust(width)
                continue
            total = sum(c[o] for o in VERDICTS)
            extra = ' '.join('%s%d' % (o[0], c[o]) for o in ('fail', 'refused', 'timeout', 'error', 'skipped') if c[o])
            line += ('%d/%d' % (c['pass'], total) + (' (%s)' % extra if extra else '')).ljust(width)
        out.append(line)
    bad = [r for r in rows if r.get('outcome') not in ('pass',)]
    out += ['', f'Failures and other non-passes ({len(bad)}):' if bad else 'No failures.']
    for r in sorted(bad, key=lambda r: (r.get('lane_no') or 0, r.get('fixture'), r.get('model'), r.get('attempt') or 0)):
        cost = []
        if r.get('calls') is not None:
            cost.append(f'{r["calls"]} calls')
        if r.get('seconds') is not None:
            cost.append(f'{round(r["seconds"])} s')
        out.append(f'- [{r.get("lane_no")} {r.get("lane")}] {r.get("fixture")} · {r.get("model")}@{r.get("node")} '
                   f'a{r.get("attempt")} · {r.get("outcome").upper()}' + (f' · {", ".join(cost)}' if cost else ''))
        out.append(f'    reason: {r.get("reason") or "(none recorded)"}')
        if r.get('supersedes'):
            out.append(f'    rejudged {r.get("rejudged")} from the saved output; recorded first as '
                       f'{str((r.get("was") or {}).get("outcome")).upper()}')
        failed = (r.get('checks') or {}).get('failed_unit')
        if failed:
            ex = failed.get('first_failing_example') or {}
            example = (f'{ex.get("call")} expected {ex.get("expected")} got {ex.get("got")}' if ex.get('call')
                       else f'error: {ex.get("error")}')
            out.append(f'    failed unit: {failed.get("unit")} (line {failed.get("line")}) after {failed.get("calls")} calls, '
                       f'temperatures {failed.get("temps")}')
            out.append(f'    first failing example (last attempt): {one_line(example, 400)}')
            out.append(f'    reply, first 200 characters: {json.dumps(failed.get("reply_head"), ensure_ascii=False)}')
        if r.get('evidence'):
            out.append(f'    evidence: {r["evidence"]}')
    specs = [r for r in rows if r.get('lane') == 'spec' and (r.get('checks') or {}).get('per_unit') is not None]
    if specs:
        out += ['', 'Spec builds (units accepted; retries; the kernel fixes at work):']
        for r in specs:
            c = r['checks']
            units = c['per_unit']
            retried = [u for u in units if u.get('retries')]
            hot = sum(u.get('resampled_retries') or 0 for u in units)
            h = c.get('harness') or {}
            whole = (f'whole page {h.get("pass")}/{h.get("cases")} documents, plain {h.get("plain")}/{h.get("plainOf")}'
                     if h else 'whole page not built')
            out.append(f'- {r.get("fixture")} · {r.get("model")}@{r.get("node")} a{r.get("attempt")} · '
                       f'{str(r.get("outcome")).upper()} · units {c.get("units_accepted")}/{c.get("units_total")} · '
                       f'{r.get("calls")} calls · {round(r.get("seconds") or 0)} s · {whole}')
            out.append(f'    units needing retries: {len(retried)}'
                       + (' (' + ', '.join(f'{u["unit"][5:]} {u["retries"]}' for u in retried) + ')' if retried else '')
                       + f'; retries re-sampled (new temperature or seed): {hot} of {sum(u.get("retries") or 0 for u in units)}; '
                       f'byte-identical repeated replies: {sum(u["identical"] for u in units)}')
            if r.get('settings'):
                out.append(f'    settings {json.dumps(r["settings"], sort_keys=True)}; limits {json.dumps(r.get("limits"), sort_keys=True)}')
            code = r.get('code_sha256') or {}
            if code:
                out.append('    code sha256: ' + ', '.join(f'{k} {str(v)[:12]}' for k, v in code.items()
                                                          if k in REPORTED_CODE))
            if r.get('code_changed_during_trial'):
                out.append(f'    CODE CHANGED DURING THE TRIAL: {", ".join(r["code_changed_during_trial"])}')
    notes = [r for r in rows if r.get('outcome') == 'pass' and r.get('calls') == 0]
    if notes:
        out += ['', 'Passes with zero model calls (the kernel decided alone; not a model result):']
        out += [f'- {r.get("fixture")} · {r.get("model")}@{r.get("node")} a{r.get("attempt")}' for r in notes]
    lost, running = interrupted(rows if all_rows is None else all_rows, Path(ledger_path).parent / 'runs', alive)
    if batches:
        lost = [n for n in lost if any(n.startswith(b + '-') for b in batches)]
        running = [n for n in running if any(n.startswith(b + '-') for b in batches)]
    if running:
        out += ['', 'Running now (started, no row yet):'] + [f'- {name}' for name in running]
    if lost:
        out += ['', 'Interrupted trials (started, no row, and their batch process has ended; no verdict):']
        out += [f'- {name}' for name in lost]
    return '\n'.join(out)


def beta_alive(pid=None):
    """Is the trial's batch process still running? Older intent files carry no pid: then any other process of
    this script counts."""
    pids = [pid] if pid else [int(d.name) for d in Path('/proc').iterdir() if d.name.isdigit()]
    for p in pids:
        if p == os.getpid():
            continue
        try:
            cmdline = Path(f'/proc/{p}/cmdline').read_bytes()
            if b'symblic.bench.local_beta' in cmdline or b'bench/local_beta.py' in cmdline:
                return True
        except (OSError, ValueError):
            continue
    return False


def interrupted(rows, runs_dir, alive=None):
    """Trial folders with an intent file and no ledger row -> (interrupted, running)."""
    alive = alive or beta_alive
    ids = {r.get('id') for r in rows} | {str(r.get('evidence') or '').rpartition('/')[2] for r in rows}
    lost, running = [], []
    try:
        folders = sorted(d for d in Path(runs_dir).iterdir() if (d / 'intent.json').exists() and d.name not in ids)
    except OSError:
        return [], []
    for d in folders:
        try:
            pid = json.loads((d / 'intent.json').read_text()).get('pid')
        except (OSError, ValueError, AttributeError):
            pid = None
        (running if alive(pid) else lost).append(d.name)
    return lost, running


def _size(model):
    m = re.search(r'(\d+(?:\.\d+)?)b\b', str(model).lower())
    return float(m.group(1)) if m else 0.0


# ------------------------------------------------------------------ entry

def main(argv=None):
    """Command line (see the module docstring). Exit 0 on success, 2 when the configuration refuses."""
    ap = argparse.ArgumentParser(prog='python3 -m symblic.bench.local_beta', description=__doc__.split('\n\n')[0])
    ap.add_argument('--config', default=None,
                    help='configuration JSON (default: $SYMBLIC_LOCAL_BETA_CONFIG or data/local_beta/config.example.json)')
    ap.add_argument('--state', default=os.environ.get('SYMBLIC_LOCAL_BETA_STATE') or str(DEFAULT_STATE),
                    help='folder for ledger.jsonl and the per-trial evidence folders')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('fixtures')
    for name in ('plan', 'batch'):
        p = sub.add_parser(name)
        p.add_argument('--batch', default='first', help='a batch name from the configuration')
        p.add_argument('--pair', action='append', help='MODEL@NODE (repeat); default: the batch pairs')
        p.add_argument('--allow-reserved', action='store_true')
        p.add_argument('--hot-wait', type=int, default=600)
        p.add_argument('--busy-wait', type=int, default=900)
        p.add_argument('--batch-id', help='label for the rows (default: the start minute, YYYYmmddTHHMM)')
    t = sub.add_parser('trial')
    t.add_argument('--lane', required=True, choices=sorted(LANES))
    t.add_argument('--fixture', required=True)
    t.add_argument('--pair', required=True, help='MODEL@NODE')
    t.add_argument('--allow-reserved', action='store_true')
    t.add_argument('--approve-over-hour', action='store_true', help='ladder only: run a session estimated past one hour')
    t.add_argument('--hot-wait', type=int, default=600)
    t.add_argument('--busy-wait', type=int, default=900)
    t.add_argument('--batch-id', help='label for the row (default: the start minute, YYYYmmddTHHMM)')
    j = sub.add_parser('rejudge', help='judge a row whose run did not finish again from its saved output (new row)')
    j.add_argument('id')
    r = sub.add_parser('report')
    r.add_argument('--json', action='store_true')
    r.add_argument('--batch', action='append', help='only rows of this batch id (repeat); default: every row')
    a = ap.parse_args(argv)
    try:
        cfg = use_config(a.config)
    except PolicyError as e:
        print(f'refused: {e}', file=sys.stderr)
        return 2
    state = Path(a.state).expanduser()
    ledger = Ledger(state / 'ledger.jsonl')
    log = lambda msg: print(time.strftime('%H:%M:%S ') + msg, file=sys.stderr, flush=True)   # noqa: E731
    try:
        if a.cmd == 'fixtures':
            for name, fx in cfg.fixtures.items():
                print(f'{LANES[fx["lane"]]} {fx["lane"]:<9} {name:<20} {fx.get("path") or fx.get("question")}')
                if fx.get('expect') or fx.get('expect_result'):
                    print(f'{"":<32}expect {json.dumps(fx.get("expect") or fx.get("expect_result"))}')
                if fx.get('note'):
                    print(f'{"":<32}{fx["note"]}')
            return 0
        if a.cmd == 'rejudge':
            rows = ledger.rows()
            row = next((x for x in rows if x.get('id') == a.id), None)
            if row is None:
                raise PolicyError(f'no row {a.id}')
            if any(x.get('supersedes') == a.id for x in rows):
                raise PolicyError(f'{a.id} was already rejudged')
            new = ledger.append(rejudge(row))
            print(json.dumps({k: new.get(k) for k in ('id', 'supersedes', 'outcome', 'reason', 'was')}, indent=1,
                             ensure_ascii=False))
            return 0
        if a.cmd == 'report':
            rows = effective([x for x in ledger.rows() if not a.batch or x.get('batch') in a.batch])
            if a.json:
                board = {f'{no} {lane}': cells for (no, lane), cells in sorted(scoreboard(effective(rows)).items())}
                lost, running = interrupted(ledger.rows(), ledger.path.parent / 'runs')
                print(json.dumps({'ledger': str(ledger.path), 'rows': len(rows), 'scoreboard': board,
                                  'failures': [{k: x.get(k) for k in ('id', 'lane', 'fixture', 'model', 'node',
                                                                      'attempt', 'outcome', 'reason', 'evidence')}
                                               for x in rows if x.get('outcome') != 'pass'],
                                  'running': running, 'interrupted': lost}, indent=1))
            else:
                print(render_report(rows, ledger.path, all_rows=ledger.rows(), batches=a.batch))
            return 0
        if a.cmd == 'trial':
            model, node = parse_pair(a.pair)
            row = Trial(a.lane, a.fixture, model, node, state=state, env=Env(cfg), ledger=ledger,
                        batch=a.batch_id or time.strftime('%Y%m%dT%H%M'), allow_reserved=a.allow_reserved, log=log,
                        hot_wait=a.hot_wait, busy_wait=a.busy_wait, approve_over_hour=a.approve_over_hour).run()
            print(json.dumps(row, indent=1, ensure_ascii=False, default=str))
            return 0
        trials = batch_trials(a.batch, a.pair)
        for lane, fixture, model, node, _ in trials:
            check_policy(model, node, a.allow_reserved)
        if a.cmd == 'plan':
            for lane, fixture, model, node, options in trials:
                print(f'{node}  {LANES[lane]} {lane:<9} {fixture:<18} {applicator(model, node)}'
                      + (f'  {json.dumps(options, sort_keys=True)}' if options else ''))
            return 0
        batch = a.batch_id or time.strftime('%Y%m%dT%H%M')
        log(f'batch {batch}: {len(trials)} trials on {", ".join(sorted({t[3] for t in trials}))}; ledger {ledger.path}')
        rows = run_batch(trials, state=state, env=Env(cfg), ledger=ledger, batch=batch, allow_reserved=a.allow_reserved,
                         log=log, hot_wait=a.hot_wait, busy_wait=a.busy_wait, batch_name=a.batch)
        log(f'batch {batch} done: ' + ', '.join(f'{o} {sum(1 for x in rows if x.get("outcome") == o)}'
                                                for o in OUTCOMES if any(x.get('outcome') == o for x in rows)))
        print(render_report([x for x in ledger.rows() if x.get('batch') == batch], ledger.path,
                            all_rows=ledger.rows(), batches=[batch]))
        return 0
    except PolicyError as e:
        print(f'refused: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
