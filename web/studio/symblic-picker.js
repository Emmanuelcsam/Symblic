/* symblic-picker: choose agents for Symblic asks from the existing cache-only engine catalogue
   (GET /api/runner/engines on the host; refresh only on an explicit click). Builds exact applicator text
   (engine[:model][@node][+effort][*weight], lists, groups, votes / route=escalate / route=search, councils) and
   shows it before applying. No innerHTML; nothing runs here: execution stays on the existing applicator paths. */
(() => {
  'use strict';
  const ENGINES = '/api/runner/engines';
  const REFRESH = '/api/runner/engines/refresh';
  const COUNCILS = ['council:panel', 'council:debate', 'council:chain', 'council:layers'];
  // maker by model-name prefix, as the host's agent page grouped its Ollama list
  const MAKERS = [['deepseek', 'DeepSeek'], ['codegemma', 'Google'], ['gemma', 'Google'], ['codellama', 'Meta'], ['llama', 'Meta'],
    ['qwen', 'Alibaba (Qwen)'], ['phi', 'Microsoft'], ['granite', 'IBM'], ['mistral', 'Mistral'], ['mixtral', 'Mistral'],
    ['smollm', 'Hugging Face'], ['olmo', 'Allen AI'], ['nemotron', 'NVIDIA']];
  let sheet = null, rows = [], councils = [], catalogueErrors = [], crew = [], mode = 'one', opts = { votes: 2, samples: 6, rounds: 2 };
  // v3: every open and close starts a new generation; async work (a catalogue load, a machine check) acts only while
  // the generation it started in is still the current one, so a closed or reopened sheet is never touched by it
  let generation = 0;
  const current = (gen) => gen === generation && sheet !== null;

  function node(tag, props, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids) if (kid !== null && kid !== undefined && kid !== false) n.append(kid);
    return n;
  }
  async function call(path, body) {
    const res = await fetch(path, body === undefined ? { credentials: 'same-origin' } : {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!res.ok) throw new Error(res.status === 403 ? 'This catalogue is only available to the owner.' : 'The engine catalogue did not answer (' + res.status + ').');
    return res.json();
  }

  const maker = (model) => { const m = (model || '').toLowerCase(); const hit = MAKERS.find(([p]) => m.startsWith(p)); return hit ? hit[1] : 'Other'; };
  const groupOf = (r) => r.kind === 'local' || r.engine === 'ollama' ? 'Local models · ' + maker(r.model)
    : r.kind === 'cli' ? 'Agent CLIs' : r.kind === 'web' ? 'Web (browser daemon)' : 'Other';
  const specOf = (r) => String(r.spec || r.id || '');
  const selectable = (r) => r.typed_ask !== false && r.selectable !== false;
  const statusOf = (r) => r.ready ? 'ready' : ({embedding_only: 'embedding only', memory_limit: 'memory limit',
    unprobed: r.installed ? 'installed · readiness unprobed' : 'unprobed'}[r.status] || String(r.status || 'unknown'));

  // the exact applicator text for one crew member
  function memberSpec(m) {
    let s = m.spec;
    if (m.effort) s += '+' + m.effort;
    if (m.weight && Number(m.weight) !== 1) s += '*' + Number(m.weight);
    return s;
  }
  const quote = (s) => JSON.stringify(s);
  function byText() {
    const specs = crew.map(memberSpec);
    if (!specs.length) return '';
    return specs.length === 1 ? 'by ' + quote(specs[0]) : 'by [' + specs.map(quote).join(', ') + ']';
  }
  function withText() {
    if (mode === 'vote') return 'with votes=' + Math.max(opts.votes, crew.length);
    if (mode === 'escalate') return 'with route=escalate';
    if (mode === 'search') return 'with route=search, samples=' + opts.samples + ', rounds=' + opts.rounds;
    return '';
  }
  function warnings() {
    const out = [];
    const council = crew.some((m) => m.spec.startsWith('council'));
    if (council && (mode === 'vote' || crew.length > 1)) out.push('A council answers as one agent but runs a whole council each time: votes and effort multiply councils.');
    if (crew.length > 25) out.push('Asks use at most 25 answers; members past that are dropped.');
    if (mode === 'one' && crew.length > 1) out.push('One agent: choose a crew mode (vote, escalate or search) for several agents.');
    if (crew.some((m) => m.row && m.row.ready === false)) out.push('Some chosen agents are not ready on any machine right now; the run waits or fails for those.');
    if (crew.some((m) => m.row && m.row.cloud)) out.push('Cloud agents need the run\'s cloud opt-in.');
    if (crew.some((m) => m.row && m.row.node === 'host' && m.row.engine === 'ollama')) out.push('You explicitly chose a model on the host machine. The existing local memory and model-wake admission checks still apply.');
    return out;
  }

  // ---- v4: native statement boundaries -----------------------------------------------------------------------------
  // An exact port of symblic.split_statements / _scan_open / _read_string / tokenize. The picker edits source only
  // where these rules give one certain answer; anything else is refused with its reason, and the text can still be
  // copied. Every edit is re-read with the same rules before it is written into the editor.
  const KEYWORDS = new Set(['program', 'note', 'section', 'module', 'use', 'given', 'let', 'define', 'term', 'fact',
    'rule', 'ask', 'ensure', 'assert', 'expect', 'if', 'elif', 'else', 'end', 'for', 'show', 'return', 'draw', 'group',
    'forget', 'pin', 'delegate', 'workflow']);
  const RAW = new Set(['program', 'workflow', 'note', 'section', 'module']);   // one-line prose headers, kept verbatim
  const BLOCK_CONT = new Set(['with', 'from', 'by', 'where']);
  const WORD_OPS = new Set(['all', 'and', 'any', 'divides', 'else', 'every', 'false', 'for', 'holds', 'if', 'iff',
    'implies', 'in', 'intersect', 'is', 'minus', 'mod', 'none', 'not', 'of', 'one', 'or', 'query', 'some', 'subset',
    'then', 'true', 'union', 'xor']);
  const OPERATORS = ['<=>', '<->', '..', '->', '=>', '==', '!=', '<=', '>=', '**', '//', '&&', '||', '+', '-', '*', '/',
    '^', '%', '<', '>', '=', '(', ')', '[', ']', '{', '}', ',', ':', '!', '|', '→', '↔', '∧', '∨', '¬', '≠', '≤', '≥',
    '∈', '∉', '∪', '∩', '∖', '⊆', '⊂', '∀', '∃', '×', '÷', '⇒', '⇔'];
  const V1_DIRECTIVE = /^use\s+[A-Za-z ]+:\s*\S/i;
  const MAX_SOURCE = 400000, MAX_STATEMENTS = 4000;
  const NAME = /[\p{L}\p{Nl}\p{No}_][\p{L}\p{N}_]*/uy;      // Python's [^\W\d]\w*
  const NUM = /\p{Nd}+(?:\.\p{Nd}+)?(?:[eE][+-]?\p{Nd}+)?/uy;
  const SAFE_SPEC = /^[A-Za-z0-9_.:@+*/-]+$/;                  // written inside "...": no quote, brace or escape
  // Python's str.isspace() set (JS trim differs at \x1c-\x1f, \x85 and ﻿)
  const PY_SPACE = new Set('\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0         '
    + '       　');
  function pyStrip(s, left = true) {
    let a = 0, b = s.length;
    if (left) while (a < b && PY_SPACE.has(s[a])) a++;
    while (b > a && PY_SPACE.has(s[b - 1])) b--;
    return s.slice(a, b);
  }
  const lower = (s) => s.toLowerCase();
  function codePointBefore(s, i) {
    const lo = s.charCodeAt(i - 1);
    if (lo >= 0xdc00 && lo <= 0xdfff && i >= 2) { const hi = s.charCodeAt(i - 2); if (hi >= 0xd800 && hi <= 0xdbff) return s.codePointAt(i - 2); }
    return lo;
  }
  const isAlnum = (cp) => /[\p{L}\p{N}]/u.test(String.fromCodePoint(cp));
  const firstWord = (stripped) => { const m = /^[A-Za-z_]+/.exec(stripped); return m ? lower(m[0]) : ''; };
  const continues = (stripped) => BLOCK_CONT.has(firstWord(stripped)) || lower(stripped).startsWith('for each ');
  const blankOrComment = (stripped) => !stripped || stripped.startsWith('#') || stripped.startsWith('//');

  function scanOpen(line, depth, inStr, triple) {        // symblic._scan_open
    let i = 0;
    while (i < line.length) {
      const ch = line[i];
      if (inStr) {
        if (triple && line.startsWith(inStr.repeat(3), i)) { inStr = null; triple = false; i += 3; continue; }
        if (!triple && ch === inStr) inStr = null;
        else if (ch === '\\') i += 1;
        i += 1;
        continue;
      }
      if (ch === '#') break;
      if (ch === '"' || ch === "'") {
        if (line.startsWith(ch.repeat(3), i)) { inStr = ch; triple = true; i += 3; continue; }
        if (ch === "'" && i > 0 && isAlnum(codePointBefore(line, i))) { i += 1; continue; }   // "sunflower's"
        inStr = ch; triple = false;
      } else if ('([{'.includes(ch)) depth += 1;
      else if (')]}'.includes(ch)) depth = Math.max(0, depth - 1);
      i += 1;
    }
    if (inStr && !triple) inStr = null;
    return [depth, inStr, triple];
  }

  // symblic.split_statements: [{start, end, kind, word}] by line index. kind 'formal', 'prose', or 'unknown' for a
  // line whose first word is not a core keyword: Symblic's own expression parser (and any loaded extension) decides
  // whether it is prose or formal. A one-line reading of it is exact unless it would run on (open bracket, triple
  // string, trailing backslash) or a continuation follows it; then `ambiguous` is that line and nothing after it is
  // edited.
  function splitStatements(source) {
    if (source.length > MAX_SOURCE) return { error: 'The program is longer than Symblic accepts.' };
    const lines = source.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    const stmts = [];
    let ambiguous = -1, i = 0;
    const mark = (at) => { if (ambiguous < 0) ambiguous = at; };
    while (i < lines.length) {
      const raw = lines[i], stripped = pyStrip(raw);
      if (blankOrComment(stripped)) { i++; continue; }
      const word = firstWord(stripped), last = stmts[stmts.length - 1];
      if (continues(stripped) && last && last.kind !== 'prose') {
        if (last.kind === 'unknown') mark(i);
        last.end = i; i++; continue;
      }
      if (RAW.has(word) || V1_DIRECTIVE.test(stripped)) { stmts.push({ start: i, end: i, kind: 'prose', word }); i++; continue; }
      if (!KEYWORDS.has(word)) {
        const [depth, inStr] = scanOpen(raw, 0, null, false);
        if (depth > 0 || inStr || pyStrip(raw, false).endsWith('\\')) mark(i);
        stmts.push({ start: i, end: i, kind: 'unknown', word }); i++; continue;
      }
      const start = i;
      let [depth, inStr, triple] = scanOpen(raw, 0, null, false), lastLine = raw;
      while ((depth > 0 || inStr || pyStrip(lastLine, false).endsWith('\\')) && i + 1 < lines.length) {
        i++; lastLine = lines[i];
        [depth, inStr, triple] = scanOpen(lastLine, depth, inStr, triple);
      }
      stmts.push({ start, end: i, kind: 'formal', word });
      i++;
    }
    if (stmts.length > MAX_STATEMENTS) return { error: 'The program has more statements than Symblic accepts.' };
    return { lines, stmts, ambiguous };
  }

  function readString(src, i) {                           // symblic._read_string: the index after it, or -1
    const q = src[i], triple = src.startsWith(q.repeat(3), i);
    let j = i + (triple ? 3 : 1);
    for (;;) {
      if (j >= src.length) return -1;
      const ch = src[j];
      if (triple && src.startsWith(q.repeat(3), j)) return j + 3;
      if (!triple && ch === q) return j + 1;
      if (!triple && ch === '\n') return -1;
      if (ch === '\\' && j + 1 < src.length) { j += 2; continue; }
      j += 1;
    }
  }
  // symblic.tokenize for one physical line: tokens with their offsets, or null where Symblic would refuse the line
  function tokenizeLine(text) {
    const toks = [];
    let i = 0;
    while (i < text.length) {
      const ch = text[i];
      if (' \t\r\\'.includes(ch)) { i++; continue; }
      if (ch === '#') break;
      if (ch === '"' || ch === "'") {
        const end = readString(text, i);
        if (end < 0) return null;
        toks.push({ kind: 'str', at: i, end }); i = end; continue;
      }
      NUM.lastIndex = i;
      let m = NUM.exec(text);
      if (m) {
        const after = i + m[0].length;
        if (after < text.length && (/\p{L}/u.test(String.fromCodePoint(text.codePointAt(after))) || text[after] === '_')) return null;
        toks.push({ kind: 'num', at: i, end: after }); i = after; continue;
      }
      if (ch === '.') {
        if (text.startsWith('..', i)) { toks.push({ kind: 'op', at: i, end: i + 2 }); i += 2; continue; }
        const rest = pyStrip(text.slice(i + 1));
        if (!rest || rest.startsWith('#')) { toks.push({ kind: 'stop', at: i, end: i + 1 }); break; }
        NAME.lastIndex = i + 1;
        if (NAME.test(text)) { toks.push({ kind: 'attr', at: i, end: i + 1 }); i++; continue; }
        return null;
      }
      NAME.lastIndex = i;
      m = NAME.exec(text);
      if (m) { toks.push({ kind: 'name', value: m[0], at: i, end: i + m[0].length }); i += m[0].length; continue; }
      const op = OPERATORS.find((o) => text.startsWith(o, i));
      if (!op) return null;
      toks.push({ kind: 'op', at: i, end: i + op.length }); i += op.length;
    }
    return toks;
  }
  const lineAt = (source, offset) => source.slice(0, Math.max(0, offset)).split('\n').length - 1;
  const names = (toks, ...words) => toks.filter((t) => t.kind === 'name' && words.includes(lower(t.value))).length;

  // The ask at `offset`, completed with `addition` (" by ... [with ...]"): {ok, reason, text}. Only a whole ask on one
  // physical line, where Symblic is certain it starts and ends there, with no by or with of its own in any spelling.
  function askEdit(source, offset, addition) {
    if (source.includes('\r')) return { ok: false, reason: 'This text has carriage returns: copy the text and edit it.' };
    const sp = splitStatements(source);
    if (sp.error) return { ok: false, reason: sp.error };
    const index = lineAt(source, offset);
    const st = sp.stmts.find((s) => s.start <= index && index <= s.end);
    if (!st || st.kind !== 'formal' || st.word !== 'ask') return { ok: false, reason: 'Put the cursor on an ask in the editor.' };
    if (sp.ambiguous >= 0 && sp.ambiguous <= st.start) {
      return { ok: false, reason: 'Line ' + (sp.ambiguous + 1) + ' can be read two ways, so where this ask starts is not certain: copy the text and edit it.' };
    }
    if (st.start !== st.end) return { ok: false, reason: 'This ask continues on other lines: copy the text and edit it.' };
    const line = sp.lines[st.start], toks = tokenizeLine(line);
    if (!toks || !toks.length) return { ok: false, reason: 'Symblic cannot read this ask yet: fix it first.' };
    if (names(toks, 'by', 'with')) return { ok: false, reason: 'This ask already says who answers it (by or with): copy the text and edit it.' };
    const stop = toks.find((t) => t.kind === 'stop'), at = stop ? stop.at : toks[toks.length - 1].end;
    const edited = line.slice(0, at).replace(/[ \t]+$/, '') + ' ' + addition + line.slice(at);
    const lines = sp.lines.slice();
    lines[st.start] = edited;
    const text = lines.join('\n');
    // the result, re-read: the same statements, this one still one whole line, now with exactly the new by/with
    const again = splitStatements(text), mine = again.stmts && again.stmts.find((s) => s.start === st.start);
    const after = tokenizeLine(edited);
    const wantWith = names(tokenizeLine('x ' + addition) || [], 'with');
    if (again.error || again.stmts.length !== sp.stmts.length || !mine || mine.end !== st.start || mine.word !== 'ask'
        || !after || names(after, 'by') !== 1 || names(after, 'with') !== wantWith) {
      return { ok: false, reason: 'The picker could not place the agents on this ask safely: copy the text and edit it.' };
    }
    return { ok: true, text, line: st.start };
  }

  // A group line inserted between whole top-level statements, after the leading program / note / section / module /
  // workflow / use statements (each consumed whole), named so that it matches no name in the program in any case.
  function groupEdit(source, members) {
    if (source.includes('\r')) return { ok: false, reason: 'This text has carriage returns: copy the text and edit it.' };
    if (!members.length || !members.every((m) => SAFE_SPEC.test(m))) return { ok: false, reason: 'These agent names cannot be written into a group safely.' };
    const sp = splitStatements(source);
    if (sp.error) return { ok: false, reason: sp.error };
    let k = 0;
    while (k < sp.stmts.length && (sp.stmts[k].word === 'use' || (sp.stmts[k].kind === 'prose' && RAW.has(sp.stmts[k].word)))) k++;
    const at = k > 0 ? sp.stmts[k - 1].end + 1 : (sp.stmts.length ? sp.stmts[0].start : sp.lines.length);
    let next = at;
    while (next < sp.lines.length && blankOrComment(pyStrip(sp.lines[next]))) next++;
    if (next < sp.lines.length && continues(pyStrip(sp.lines[next]))) {
      return { ok: false, reason: 'Line ' + (next + 1) + ' would join a group written above it: add the group by hand.' };
    }
    const used = new Set(Array.from(source.matchAll(/[\p{L}\p{Nl}\p{No}_][\p{L}\p{N}_]*/gu), (m) => lower(m[0])));
    let name = 'crew', n = 2;
    while (used.has(name) || KEYWORDS.has(name) || WORD_OPS.has(name)) name = 'crew' + n++;
    const line = 'group ' + name + ' = [' + members.map(quote).join(', ') + '].';
    const lines = sp.lines.slice();
    lines.splice(at, 0, line);
    const text = lines.join('\n');
    // the result, re-read: every earlier statement unchanged, plus exactly this one-line group where it was put
    const again = splitStatements(text);
    const body = (r, s) => r.lines.slice(s.start, s.end + 1).join('\n');
    const before = sp.stmts.map((s) => body(sp, s)), now = again.stmts ? again.stmts.map((s) => body(again, s)) : [];
    const expected = [...before.slice(0, k), line, ...before.slice(k)];
    if (again.error || now.length !== expected.length || now.some((t, i) => t !== expected[i])) {
      return { ok: false, reason: 'The picker could not place the group safely: add it by hand.' };
    }
    return { ok: true, text, name, line };
  }

  // v5 (review picker-v4, paper mode): direct edits only in a program. The format is explicit: open({format}) or the
  // page's own decision (window.SymblicFormat, the page's isPaper); never guessed here. A paper (.symd) keeps its
  // statements in fenced blocks, so editing it as a program would turn the edit into prose; unknown refuses too.
  const FORMATS = ['program', 'paper'];
  let openFormat = null;
  function formatOf(text) {
    if (openFormat !== null) return openFormat;
    const page = typeof window.SymblicFormat === 'function' ? window.SymblicFormat(text) : null;
    return FORMATS.includes(page) ? page : 'unknown';
  }
  const NOT_PROGRAM = {
    paper: 'This is a paper (.symd): its statements live in fenced symblic blocks, so the picker does not edit it. Copy the text into a block, or use it for the whole run.',
    unknown: 'The page did not say whether this is a program or a paper, so the picker does not edit it: copy the text.',
  };
  function apply(kind) {
    const ta = document.getElementById('sySrc');
    if (!ta) return note('Open the Write tab first.');
    if (kind !== 'run' && formatOf(ta.value) !== 'program') return note(NOT_PROGRAM[formatOf(ta.value)]);
    if (kind === 'run') {
      const field = document.getElementById('syBy');
      if (!field || crew.length !== 1 || mode !== 'one') return;   // never drop chosen ask options silently
      field.value = memberSpec(crew[0]);
      field.dispatchEvent(new Event('change', { bubbles: true }));
      return close();
    }
    if (kind === 'group') {
      const got = groupEdit(ta.value, crew.map(memberSpec));
      if (!got.ok) return note(got.reason);
      ta.value = got.text;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      note('Inserted "' + got.line + '". Add  by ' + got.name + (withText() ? ' ' + withText() : '') + '  to the asks that should use it.');
      return render();
    }
    if (kind === 'ask') {
      const got = askEdit(ta.value, ta.selectionStart || 0, addition());
      if (!got.ok) return note(got.reason);
      ta.value = got.text;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      return close();
    }
  }
  const addition = () => [byText(), withText()].filter(Boolean).join(' ');
  function note(text) {
    if (window.Studio && typeof window.Studio.toast === 'function') window.Studio.toast(text);
    else if (sheet) sheet.querySelector('.sp-note').textContent = text;
  }

  function render() {
    if (!sheet) return;
    const body = sheet.querySelector('.sp-body');
    body.replaceChildren();
    // crew
    const crewBox = node('section', { class: 'sp-crew', 'aria-label': 'Chosen agents' }, node('h3', { text: 'Your crew (' + crew.length + ')' }));
    if (!crew.length) crewBox.append(node('p', { class: 'sp-hint', text: 'Add agents from the list below. One agent can be the default for the whole run; several work together on one ask.' }));
    crew.forEach((m, i) => {
      const efforts = (m.row && m.row.efforts) || [];
      const effort = node('select', { class: 'field sp-small', 'aria-label': 'Effort for ' + m.spec, onchange: (e) => { m.effort = e.target.value; render(); } },
        node('option', { value: '', text: 'default effort' }), ...efforts.filter(Boolean).map((e) => node('option', { value: e, text: e, selected: m.effort === e })));
      const weight = node('input', { class: 'field sp-small', type: 'number', min: '0.1', max: '10', step: '0.5', value: String(m.weight || 1),
        'aria-label': 'Vote weight for ' + m.spec, onchange: (e) => { m.weight = Math.min(10, Math.max(0.1, Number(e.target.value) || 1)); render(); } });
      crewBox.append(node('div', { class: 'sp-member' },
        node('code', { text: memberSpec(m) }), effort, weight,
        node('button', { class: 'btn ghost', type: 'button', text: '↑', 'aria-label': 'Move up', disabled: i === 0, onclick: () => { crew.splice(i - 1, 0, crew.splice(i, 1)[0]); render(); } }),
        node('button', { class: 'btn ghost', type: 'button', text: '×', 'aria-label': 'Remove ' + m.spec, onclick: () => { crew.splice(i, 1); render(); } })));
    });
    body.append(crewBox);
    // mode
    const modes = [['one', 'One agent'], ['vote', 'Vote'], ['escalate', 'Escalate (in order)'], ['search', 'Search (checked attempts)']];
    const modeBox = node('div', { class: 'sp-modes', role: 'radiogroup', 'aria-label': 'How the crew works together' },
      ...modes.map(([id, label]) => node('label', { class: 'check' },
        node('input', { type: 'radio', name: 'sp-mode', value: id, checked: mode === id, onchange: () => { mode = id; render(); } }), ' ' + label)));
    body.append(modeBox);
    const num = (key, label, min, max) => node('label', { class: 'sp-num' }, label + ' ',
      node('input', { class: 'field sp-small', type: 'number', min, max, value: String(opts[key]), onchange: (e) => { opts[key] = Math.min(max, Math.max(min, Math.round(Number(e.target.value) || min))); render(); } }));
    if (mode === 'vote') body.append(num('votes', 'answers (votes)', Math.max(1, crew.length), 25));
    if (mode === 'search') body.append(num('samples', 'attempts per round', 1, 25), num('rounds', 'rounds', 1, 20));
    // generated text and actions
    const text = byText() ? [byText(), withText()].filter(Boolean).join(' ') : '';
    body.append(node('h3', { text: 'Symblic text' }), node('pre', { class: 'sp-text', text: text || '(choose at least one agent)' }));
    for (const w of warnings()) body.append(node('p', { class: 'sp-warn', text: w }));
    const ta = document.getElementById('sySrc');
    const unsafe = crew.some((m) => !SAFE_SPEC.test(memberSpec(m))) ? 'An agent name here has characters the picker cannot write into a program safely: copy the text.' : '';
    const format = ta ? formatOf(ta.value) : 'unknown';
    const refused = format === 'program' ? null : { ok: false, reason: NOT_PROGRAM[format] };
    const hit = ta && crew.length && !unsafe ? refused || askEdit(ta.value, ta.selectionStart || 0, addition()) : null;
    const grp = ta && crew.length >= 2 && !unsafe ? refused || groupEdit(ta.value, crew.map(memberSpec)) : null;
    if (mountApply) {
      body.append(node('div', { class: 'sp-actions' }, node('button', { class: 'btn acc', type: 'button', text: 'Use this', disabled: !text,
        onclick: () => { const fn = mountApply, format = openFormat || 'unknown'; close(); fn(text, crew.map(memberSpec), mode, format); } })));
      body.append(node('p', { class: 'sp-note', role: 'status' }));
    } else body.append(node('div', { class: 'sp-actions' },
      node('button', { class: 'btn acc', type: 'button', text: 'Use for the whole run', disabled: crew.length !== 1 || mode !== 'one', onclick: () => apply('run'),
        title: mode !== 'one' ? 'The run default is one agent: votes, escalate and search belong to an ask. Apply to an ask or insert a group.'
          : 'Sets the run\'s default agent; asks with their own "by" keep theirs.' }),
      node('button', { class: 'btn', type: 'button', text: 'Apply to the ask at the cursor', disabled: !(hit && hit.ok), onclick: () => apply('ask'),
        title: unsafe || (hit ? (hit.ok ? 'Adds these agents to the ask at the cursor.' : hit.reason) : 'Choose an agent, then put the cursor on an ask in the editor.') }),
      node('button', { class: 'btn', type: 'button', text: 'Insert as a group', disabled: !(grp && grp.ok), onclick: () => apply('group'),
        title: crew.length < 2 ? 'A group needs two or more agents.' : unsafe || (grp && !grp.ok ? grp.reason : 'Writes a group line near the top of the program.') }),
      node('button', { class: 'btn ghost', type: 'button', text: 'Copy text', disabled: !text, onclick: () => navigator.clipboard && navigator.clipboard.writeText(text).then(() => note('Copied.')) })));
    // v4: why an edit is not offered, in words (a disabled button's tooltip is unreachable on touch)
    const why = unsafe || (hit && !hit.ok ? hit.reason : '') || (grp && !grp.ok ? grp.reason : '');
    if (!mountApply && why) body.append(node('p', { class: 'sp-hint sp-why', text: why }));
    if (!mountApply) body.append(node('p', { class: 'sp-note', role: 'status' }));
    // catalogue
    const groups = new Map();
    for (const r of rows) { const g = groupOf(r); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(r); }
    const list = node('section', { class: 'sp-list', 'aria-label': 'Available agents' }, node('h3', { text: 'Available agents' }));
    const search = node('input', { class: 'field sp-filter', type: 'search', placeholder: 'Search model, maker or machine',
      'aria-label': 'Search available agents', oninput: () => {
        const needle = search.value.toLowerCase().trim();
        list.querySelectorAll('.sp-group').forEach((group) => {
          group.querySelectorAll('.sp-row').forEach((row) => { row.hidden = !(group.querySelector('summary').textContent + ' ' + row.textContent).toLowerCase().includes(needle); });
          group.hidden = ![...group.querySelectorAll('.sp-row')].some((row) => !row.hidden);
        });
      } });
    list.append(search);
    if (catalogueErrors.length) list.append(node('p', { class: 'sp-warn', text: 'Some inventory metadata could not be read. Saved choices are retained; Check the machines reports discovery failures.' }));
    if (!rows.length) list.append(node('p', { class: 'sp-hint', text: 'No cached engines yet. Use "Check the machines" to look again (no model is loaded).' }));
    for (const [g, rs] of [...groups].sort()) {
      const box = node('details', { class: 'sp-group', open: true }, node('summary', { text: g + ' (' + rs.length + ')' }));
      for (const r of rs) {
        const status = statusOf(r);
        box.append(node('div', { class: 'sp-row' },
          node('span', { class: 'sp-title', text: r.title || specOf(r) }), node('code', { text: specOf(r) }),
          node('span', { class: 'sp-badge sp-' + (r.ready ? 'ready' : 'other'), text: status, title: r.note || '' }),
          node('button', { class: 'btn', type: 'button', text: 'Add', disabled: !selectable(r), 'aria-label': 'Add ' + specOf(r), onclick: () => { if (!selectable(r)) return; crew.push({ spec: specOf(r), row: r, effort: r.default_effort || '', weight: 1 }); render(); } }),
          r.note ? node('span', { class: 'sp-row-note', text: r.note }) : null));
      }
      list.append(box);
    }
    const cbox = node('details', { class: 'sp-group', open: true }, node('summary', { text: 'Councils (a whole council of the host\'s agents answers one ask)' }));
    for (const c of councils) cbox.append(node('div', { class: 'sp-row' }, node('code', { text: c }),
      node('button', { class: 'btn', type: 'button', text: 'Add', 'aria-label': 'Add ' + c, onclick: () => { crew.push({ spec: c, row: null, effort: '', weight: 1 }); render(); } })));
    list.append(cbox);
    body.append(list);
  }

  // fetches the catalogue; the caller assigns it only if its generation is still current
  let catalogueRequested = 0, catalogueAccepted = 0;
  async function fetchCatalogue() {
    const sequence = ++catalogueRequested;
    const data = await call(ENGINES);
    const named = (data.councils || []).map((c) => (typeof c === 'string' ? c : c && (c.spec || c.id))).filter((c) => typeof c === 'string' && c.startsWith('council'));
    return { rows: (data.engines || []).filter((r) => r && (r.typed_ask !== false || r.engine === 'ollama') && specOf(r)), councils: [...new Set([...COUNCILS, ...named])],
      errors: Array.isArray(data.errors) ? data.errors : [], sequence,
      retainedInventory: typeof data.model_sources?.ollama?.installed_count === 'number' };
  }
  function adopt(got) {
    if (got.sequence < catalogueAccepted) return;
    catalogueAccepted = got.sequence;
    rows = got.rows; councils = got.councils; catalogueErrors = got.errors; syncChoices();
  }
  // The same discovered choices serve Write, Logic and Interpreter. Mounting
  // reads metadata only; refresh is an explicit button and never starts a model.
  const choices = new Set();
  function syncChoices() {
    for (const control of choices) {
      if (!control.root.isConnected) { choices.delete(control); continue; }
      control.paint();
    }
  }
  function mountChoices(target, options = {}) {
    const root = node('div', { class: 'sp-choices' });
    target.replaceChildren(root);
    const value = () => String(typeof options.getValue === 'function' ? options.getValue() || '' : '');
    const disabled = () => typeof options.disabled === 'function' ? options.disabled() : options.disabled === true;
    const search = node('input', { class: 'field', type: 'search', placeholder: 'Search installed models or agents',
      'aria-label': options.searchLabel || 'Search applicators', oninput: () => paint() });
    const select = node('select', { class: 'field', 'aria-label': options.label || 'Discovered applicators', onchange: () => {
      if (disabled()) return;
      if (typeof options.onSelect === 'function') options.onSelect(select.value);
      paint();
    } });
    const status = node('p', { class: 'hint', role: 'status', text: 'Loading cached model inventory…' });
    const detail = node('p', { class: 'hint sp-choice-detail' });
    let checking = false;
    const refreshBtn = node('button', { class: 'btn ghost', type: 'button', text: 'Check installed models', onclick: async () => {
      if (checking || disabled()) return;
      checking = refreshBtn.disabled = true;
      const valid = () => root.isConnected;
      try {
        const result = await call(REFRESH, {});
        if (!valid()) return;
        if (!result.accepted && !result.coalesced) throw new Error('The machines were not checked: ' + (result.reason || 'unavailable') + '.');
        let finished = false, partial = false;
        for (let i = 0; i < 300 && valid(); i++) {
          await new Promise(resolve => setTimeout(resolve, 2000));
          if (!valid()) return;
          const job = (await call(REFRESH)).refresh || {};
          if (!valid()) return;
          status.textContent = 'Checking installed models… ' + (job.completed || 0) + '/' + (job.total || '?');
          if (!job.active) {
            finished = true;
            partial = job.state === 'failed' || job.state === 'partial';
            break;
          }
        }
        if (!valid()) return;
        if (!finished) throw new Error('The metadata check is still running. Open Choose agents to check its status.');
        const got = await fetchCatalogue();
        if (!valid()) return;
        adopt(got); if (sheet) render();
        describe(got);
        if (partial) status.textContent += ' Some machine checks failed; earlier installed tags remain visible without readiness.';
      } catch (error) { if (valid()) status.textContent = error.message; }
      finally { checking = false; if (valid()) refreshBtn.disabled = disabled(); }
    } });
    function describe(got) {
      const local = rows.filter(r => r.engine === 'ollama');
      const names = new Set(local.filter(selectable).map(r => r.model));
      status.textContent = names.size + ' installed answer models · ' + local.length + ' model placements. '
        + (!local.length ? 'Use Check installed models to discover local and fleet tags. ' : '')
        + (got.errors.length ? 'Some inventory metadata is unavailable. ' : '')
        + (!got.retainedInventory && !local.length ? 'This server does not report retained local inventory; restart it after installing the catalog update. ' : '')
        + 'Selecting a model does not load it.';
    }
    function paint() {
      const selected = value(), needle = search.value.trim().toLowerCase();
      select.replaceChildren(node('option', { value: '', text: options.emptyLabel || 'Select an installed model or agent…' }));
      const groups = new Map();
      let present = !selected;
      for (const row of rows) {
        const spec = specOf(row), group = groupOf(row);
        if (spec !== selected && needle && !(group + ' ' + row.title + ' ' + spec).toLowerCase().includes(needle)) continue;
        if (!groups.has(group)) { const item = node('optgroup', { label: group }); groups.set(group, item); select.append(item); }
        groups.get(group).append(node('option', { value: spec, disabled: !selectable(row),
          text: (row.title || spec) + ' · ' + statusOf(row) }));
        if (spec === selected) present = true;
      }
      if (!present) select.append(node('option', { value: selected, text: selected + ' · current choice; not in cached inventory' }));
      select.value = selected;
      select.disabled = search.disabled = disabled();
      refreshBtn.disabled = checking || disabled();
      const row = rows.find(r => specOf(r) === selected);
      detail.textContent = row ? (row.note || '') + (row.engine === 'ollama' && row.node === 'host'
        ? ' You selected @host explicitly; local admission still applies.' : '') : '';
    }
    root.append(search, select, refreshBtn, status, detail);
    const control = { root, paint };
    choices.add(control); paint();
    fetchCatalogue().then(got => { if (root.isConnected) { adopt(got); describe(got); } }).catch(error => {
      if (root.isConnected) status.textContent = error.message + ' Your current/manual choice is kept. Update and restart the server if the catalogue API is missing.';
    });
    return { refresh: paint, destroy: () => { choices.delete(control); root.remove(); } };
  }
  // v4: loads within one sheet are ordered as well: each takes a number when it starts, and its answer is used only
  // if no later-started load has been used already (an initial GET answering after a refresh is dropped)
  let requested = 0, accepted = 0;
  async function loadCatalogue(gen) {
    const seq = ++requested;
    const got = await fetchCatalogue();
    if (!current(gen) || seq < accepted) return false;
    accepted = seq;
    adopt(got);
    render();
    return true;
  }
  async function refresh(button) {
    const gen = generation;
    button.disabled = true;
    try {
      const got = await call(REFRESH, {});
      if (!current(gen)) return;
      if (!got.accepted && !got.coalesced) { note('The machines were not checked: ' + (got.reason || 'unavailable') + '.'); return; }
      let finalState = '';
      for (let i = 0; i < 300; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        if (!current(gen)) return;                       // closed or reopened: stop polling now
        const st = (await call(REFRESH)).refresh || {};
        if (!current(gen)) return;
        note('Checking the machines… ' + (st.completed || 0) + '/' + (st.total || '?'));
        if (!st.active) { finalState = st.state || 'unknown'; break; }
      }
      if (await loadCatalogue(gen)) note(finalState === 'done' ? 'Machines checked.'
        : finalState ? 'Some machine checks failed or were unavailable. Earlier installed tags remain visible without readiness.'
          : 'The metadata check is still running; reopen the picker to read current status.');
    } catch (e) { if (current(gen)) note(e.message); } finally { if (current(gen)) button.disabled = false; }
  }

  // v4: closing (Esc, ×, an action) gives focus back to the control that opened the sheet, when it is still there
  let opener = null;
  function close() {
    generation++;
    if (sheet) { sheet.remove(); sheet = null; }
    const back = opener;
    opener = null;
    if (back && back.isConnected && typeof back.focus === 'function') back.focus();
  }
  // options.onApply(text, specs, mode, format): another tab (Interpreter, Logic) receives the generated text and decides what
  // to do with it; the Write-tab actions are replaced by one "Use this" button. options.opener: the control that gets
  // focus back on close (default: the focused element). Without options the picker edits the Write tab.
  let mountApply = null;
  async function open(options) {
    const from = (options && options.opener) || document.activeElement;
    close();
    opener = from && from !== document.body && from !== document.documentElement ? from : null;
    mountApply = options && typeof options.onApply === 'function' ? options.onApply : null;
    // an explicit format from the caller wins; an invalid one is 'unknown' (no direct edits), never a guess
    openFormat = options && 'format' in options ? (FORMATS.includes(options.format) ? options.format : 'unknown') : null;
    crew = [];                          // every opening starts a fresh crew
    mode = 'one';
    accepted = 0;
    const refreshBtn = node('button', { class: 'btn ghost', type: 'button', text: 'Check the machines', title: 'Checks installed models on the host and the worker nodes (no model is loaded). Only when you click.' });
    refreshBtn.addEventListener('click', () => refresh(refreshBtn));
    sheet = node('aside', { class: 'sp-root sp-sheet', role: 'dialog', 'aria-label': 'Choose agents' },
      node('header', { class: 'sp-head' }, node('h2', { text: 'Choose agents' }), refreshBtn,
        node('button', { class: 'btn ghost', type: 'button', text: '×', 'aria-label': 'Close', onclick: close })),
      node('div', { class: 'sp-body' }, node('p', { class: 'sp-hint', text: 'Loading the engine catalogue…' })));
    document.body.append(sheet);
    const gen = generation;
    sheet.querySelector('button[aria-label="Close"]').focus();
    try {
      await loadCatalogue(gen);                          // ignored when closed, reopened or overtaken by a refresh
    } catch (e) {
      if (!current(gen)) return;
      if (accepted) note(e.message);                     // a newer catalogue is already shown: keep it
      else sheet.querySelector('.sp-body').replaceChildren(node('p', { class: 'sp-warn', text: e.message + ' Use "Check the machines" to try again.' }));
    }
  }
  document.addEventListener('click', (e) => { if (e.target.closest && e.target.closest('#syPick')) { e.preventDefault(); open(); } });
  // Esc closes; while the picker is open, Ctrl/Cmd+Enter in the page never starts a run from behind it
  document.addEventListener('keydown', (e) => {
    if (sheet && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && sheet) close(); });
  window.SymblicPicker = { open, close, mountChoices, syncChoices, _spec: { memberSpec, byText, withText },
    _lexical: { splitStatements, tokenizeLine, askEdit, groupEdit } };
})();
