"""Executable papers: literate Symblic (.symd) and a reproduction test across groups of agents.

A paper is Markdown. Its prose explains, its definitions fix the meaning of words, and its fenced ```symblic blocks
are the statements. Compiling it is deterministic:

    ---                                   front matter (optional): defaults for every ask
    by: ollama:qwen3:4b-instruct
    context: sections                     sections (default) | none
    ---
    # Reading a recipe                    -> program Reading a recipe.
    Prose of the introduction ...         -> the context of the asks in this section
    ## Definitions
    - **cup**: the US legal cup, 240 mL. -> term cup means "the US legal cup, 240 mL".
    ## Method                             -> section Method.  (a new section context)
    ```symblic
    ask flour: Number "How many cups of flour?" from recipe
    ```

Each section's prose becomes a weight-5 binding `section_N` (Text), and `use context=[section_N]` makes it the default
context of the asks under it, so an agent reads the paper's explanation of a step together with the step. An ask with
its own `context=` keeps its own. Definitions become `term`s: every ask whose text uses the word is shown the
definition (symblic.kernel.run.definitions_for). lint() flags vague quantities a reader would have to guess ("about 3",
"a couple of", "slowly", a percentage with no basis) unless the paper defines them.

reproduce() runs one compiled paper with several disjoint cohorts of agents (fresh records each) and lines up every
statement by fingerprint. Each statement on which the cohorts differ is traced back to the paper's line, its section
and the words it used, which is where the paper is underspecified. The paper reproduces when every cohort finishes with
the same run fingerprint. Agreement is measured, never assumed to be correctness: that is what the paper's own
ensure/assert statements are for.

Command line: python3 -m symblic.authoring.paper check|compile PAPER.symd [--json] (no model), and
reproduce PAPER.symd --cohort APP --cohort APP (asks the models). Worked papers: docs/reference/papers/.
Depends on: symblic.kernel (language, run), symblic.lang.abstraction; reproduce's runner uses
symblic.providers.applicators. Pure except reproduce()'s runner (given by the caller) and the CLI; nothing runs on
import.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys

from symblic.kernel import language as S

try:
    from symblic.lang import abstraction as symblic_lang  # noqa: F401  (registers function/routine/import/test)
except ImportError:      # pragma: no cover
    pass

MAX_PAPER = 300_000
MAX_SECTION_PROSE = 8_000
CONTEXT_BUDGET = 10_000         # characters of paper prose an ask is given by default (the capsule's is 12 000)
FENCE_RX = re.compile(r'^(\s*)(```+|~~~+)\s*([A-Za-z0-9_-]*)\s*$')
HEADING_RX = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
TERM_LIST_RX = re.compile(r'^\s*[-*+]\s+\*\*(.+?)\*\*\s*(?::|—|–|=|\bmeans\b)\s*(.+?)\s*$')
TERM_LINE_RX = re.compile(r'^\s*\*\*(.+?)\*\*\s+means\s+(.+?)\s*$')
CODE_LANGS = ('symblic', 'sym', 'symd')
DEFINITIONS_BINDING = 'paper_definitions'
FRONT_KEYS = ('by', 'effort', 'votes', 'agree', 'retries', 'budget', 'temperature', 'seed', 'tools', 'context')


class PaperError(Exception):
    def __init__(self, message: str, line: int = 0):
        super().__init__(message)
        self.message, self.line = message, line

    def as_dict(self) -> dict:
        return {'message': self.message, 'line': self.line, 'kind': 'paper'}


def _quote_triple(text: str) -> str:
    """Prose as a Symblic triple-quoted string: braces are literal, backslashes and quotes escaped."""
    text = text.replace('\\', '\\\\').replace('{', '{{').replace('}', '}}').replace('"""', '""\\"')
    if text.endswith('"'):
        text = text[:-1] + '\\"'
    return '"""' + text + '"""'


def _quote(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('{', '{{').replace('}', '}}') + '"'


def _front_matter(lines: list) -> tuple:
    """({key: value}, first body line index, warnings)."""
    if not lines or lines[0].strip() != '---':
        return {}, 0, []
    out, warnings = {}, []
    for i in range(1, min(len(lines), 60)):
        raw = lines[i].strip()
        if raw == '---':
            return out, i + 1, warnings
        if not raw or raw.startswith('#'):
            continue
        key, sep, value = raw.partition(':')
        key = key.strip().lower()
        if not sep:
            warnings.append({'line': i + 1, 'message': f'front matter line without "key: value": {raw[:60]}'})
            continue
        if key not in FRONT_KEYS:
            warnings.append({'line': i + 1, 'message': f'unknown front matter key {key!r} '
                                                       f'(known: {", ".join(FRONT_KEYS)})'})
            continue
        out[key] = value.strip().strip('"\'')
    raise PaperError('the front matter opened on line 1 has no closing ---', 1)


def _use_value(key: str, value: str) -> str:
    if key in ('votes', 'retries', 'budget', 'seed') and re.fullmatch(r'\d{1,6}', value):
        return value
    if key in ('agree', 'temperature') and re.fullmatch(r'\d+(\.\d+)?', value):
        return value
    if key in ('effort', 'tools') and re.fullmatch(r'[a-z]+', value):
        return value
    return _quote(value)


def _split(lines: list, start: int) -> tuple:
    """Pass 1: (title, title_line, sections, terms). A section is {'n', 'title', 'line', 'prose': [str],
    'code': [(first_line, [lines])]}; section 0 is the introduction (before the first sub-heading)."""
    title, title_line = None, 0
    sections = [{'n': 0, 'title': None, 'line': start + 1, 'prose': [], 'code': []}]
    terms = []
    i = start
    while i < len(lines):
        raw = lines[i]
        sec = sections[-1]
        m = FENCE_RX.match(raw)
        if m:
            fence, lang = m.group(2), m.group(3).lower()
            j = i + 1
            while j < len(lines) and not re.match(rf'^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$', lines[j]):
                j += 1
            if j >= len(lines):
                raise PaperError('a code block is not closed', i + 1)
            body = lines[i + 1:j]
            if lang in CODE_LANGS:
                sec['code'].append((i + 2, body))
            else:
                sec['prose'].append('\n'.join(lines[i:j + 1]))
            i = j + 1
            continue
        h = HEADING_RX.match(raw)
        if h:
            text_h = h.group(2).strip()
            if len(h.group(1)) == 1 and title is None:
                title, title_line = text_h, i + 1
                sec['title'] = title
            else:
                sections.append({'n': len(sections), 'title': text_h, 'line': i + 1, 'prose': [], 'code': []})
            i += 1
            continue
        t = TERM_LIST_RX.match(raw) or TERM_LINE_RX.match(raw)
        if t:
            word = t.group(1).strip().strip('*_` ')
            meaning = t.group(2).strip().rstrip('.').strip()
            if word and meaning and len(word) <= 60:
                if any(x['term'].lower() == word.lower() for x in terms):
                    raise PaperError(f'"{word}" is defined twice', i + 1)
                terms.append({'term': word, 'definition': meaning, 'paper_line': i + 1, 'section': sec['n']})
                i += 1
                continue
        sec['prose'].append(raw)
        i += 1
    return title, title_line, sections, terms


def compile_paper(text: str) -> dict:
    """{'source', 'map': [{'line', 'paper_line', 'section', 'kind'}], 'sections': [...], 'terms': [...],
    'title', 'warnings', 'sha256'}. Raises PaperError on a malformed paper; Symblic errors in the code
    blocks are reported by check_paper (with paper line numbers).

    Order of the program: front-matter defaults, the title, every definition (a paper's definitions hold
    everywhere in it, wherever they are written), then each section: its header, and before its first
    statement the context its asks read by default (the introduction and all of the section's prose)."""
    if len(text) > MAX_PAPER:
        raise PaperError(f'the paper is too long ({len(text)} characters; the limit is {MAX_PAPER})')
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    front, start, warnings = _front_matter(lines)
    context_mode = (front.pop('context', 'sections') or 'sections').lower()
    if context_mode not in ('sections', 'section', 'none'):
        raise PaperError('context in the front matter is "sections" (everything up to the ask), "section" (the '
                         'introduction and the ask\'s own section) or "none"', 1)
    title, title_line, sections, terms = _split(lines, start)
    out: list = []                  # compiled lines
    smap: list = []                 # per compiled line

    def emit(source_text: str, paper_line: int, kind: str, section: int):
        for k, piece in enumerate(source_text.split('\n')):
            out.append(piece)
            smap.append({'line': len(out), 'paper_line': paper_line + (k if kind == 'code' else 0),
                         'section': section, 'kind': kind})

    def prose_text(sec) -> str:
        if 'text' not in sec:
            prose = re.sub(r'\n{3,}', '\n\n', '\n'.join(sec['prose']).strip())
            if len(prose) > MAX_SECTION_PROSE:
                warnings.append({'line': sec['line'], 'message': f'section "{sec["title"] or title}" has '
                                 f'{len(prose)} characters of prose; only the first {MAX_SECTION_PROSE} are context'})
                prose = prose[:MAX_SECTION_PROSE]
            sec['text'] = prose
        return sec['text']

    def prose_binding(sec) -> str | None:
        """`let section_N: Text = ...` once for a section with prose; its name, or None."""
        if 'binding' in sec:
            return sec['binding']
        prose = prose_text(sec)
        sec['binding'] = None
        if not prose or context_mode == 'none':
            return None
        sec['binding'] = f'section_{sec["n"]}'
        emit(f'let {sec["binding"]}: Text = {_quote_triple(prose)} with weight=5.', sec['line'], 'context', sec['n'])
        return sec['binding']

    def context_for(sec) -> list:
        """What an ask in `sec` reads by default, in reading order. A reader of a paper has read everything
        before the step (`sections`): the definitions, the introduction, every earlier section and its own,
        nearest first when they do not all fit CONTEXT_BUDGET (the definitions and its own section always
        do). `section`: the introduction and its own section only."""
        own = sec if sec['n'] else None
        earlier = [] if context_mode == 'section' else [x for x in sections[1:sec['n']] if prose_text(x)]
        used = len(defs_text) + (len(prose_text(own)) if own else 0)
        keep = []
        for cand in ([sections[0]] if sections[0] is not own else []) + list(reversed(earlier)):
            size = len(prose_text(cand))
            if not size:
                continue
            if used + size > CONTEXT_BUDGET:
                warnings.append({'line': sec['line'], 'message': f'section "{cand["title"] or title}" is left out of '
                                 f'the context of "{sec["title"] or title}" (over {CONTEXT_BUDGET} characters)'})
                continue
            used += size
            keep.append(cand)
        keep.sort(key=lambda x: x['n'])
        names = [defs_binding] if defs_binding else []
        names += [prose_binding(x) for x in keep] + ([prose_binding(own)] if own and prose_text(own) else [])
        return [n for n in names if n]

    for key, value in front.items():
        emit(f'use {key}={_use_value(key, value)}.', 1, 'front', 0)
    if title:
        emit(f'program {re.sub(r"[.#]", "", title)}.', title_line, 'header', 0)
    for t in terms:
        emit(f'term {_quote(t["term"])} means {_quote(t["definition"])}.', t['paper_line'], 'term', t['section'])
    # Every definition also reaches every ask as context: a term attaches by itself only when the ask's own
    # instruction uses the word, but a paper's words are often in what the ask reads (from ...), and a
    # paper's definitions hold everywhere in it.
    defs_binding, defs_text = None, ''
    if terms and context_mode != 'none':
        listing = '\n'.join(f'- {t["term"]}: {t["definition"]}' for t in terms)
        defs_binding = DEFINITIONS_BINDING
        defs_text = 'DEFINITIONS (they hold everywhere in this paper)\n' + listing
        emit(f'let {defs_binding}: Text = {_quote_triple(defs_text)} with weight=5.', terms[0]['paper_line'],
             'context', terms[0]['section'])
    for sec in sections:
        if sec['n'] and sec['title']:
            emit(f'section {re.sub(r"[#]", "", sec["title"])}.', sec['line'], 'header', sec['n'])
        if not sec['code']:
            continue
        if context_mode == 'none':
            names = []
        else:
            names = context_for(sec)
        emit(f'use context=[{", ".join(names)}].' if names else 'use context=none.', sec['line'], 'context', sec['n'])
        for first, body in sec['code']:
            indent = min((len(b) - len(b.lstrip()) for b in body if b.strip()), default=0)
            emit('\n'.join(b[indent:] for b in body), first, 'code', sec['n'])
    for sec in sections:
        sec['prose_chars'] = len('\n'.join(sec['prose']).strip())
        sec['code_blocks'] = len(sec['code'])
    source = '\n'.join(out) + '\n'
    return {'source': source, 'map': smap, 'title': title or 'Untitled paper', 'terms': terms, 'warnings': warnings,
            'sections': [{k: v for k, v in s.items() if k not in ('prose', 'code', 'text')} for s in sections],
            'context': context_mode, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def paper_line(compiled: dict, line: int) -> dict:
    """The paper position of a compiled line: {'paper_line', 'section', 'section_title', 'kind'}."""
    row = compiled['map'][line - 1] if 0 < line <= len(compiled['map']) else {'paper_line': 0, 'section': 0,
                                                                              'kind': 'unknown'}
    sec = compiled['sections'][row['section']] if row['section'] < len(compiled['sections']) else {}
    return {'paper_line': row['paper_line'], 'section': row['section'], 'section_title': sec.get('title') or
            compiled['title'], 'kind': row['kind']}


# Vague quantities a reader has to guess (measured: each of these made agents disagree or silently agree
# on a default; LANGUAGE-3 §7). A phrase the paper defines is not reported.
VAGUE = [
    (re.compile(r'\b\d+(?:\.\d+)?\s?%(?!\s*(?:w/w|w/v|v/v|by (?:mass|weight|volume)|of\b))', re.I),
     'a percentage with no basis: say w/w, w/v, v/v, or "% of <what>"', 'percent'),
    (re.compile(r'\b(?:about|approximately|approx\.?|roughly|around|~)\s*\d', re.I),
     'an approximate number: give the value (and a tolerance if it matters)', 'approx'),
    (re.compile(r'\b(?:a few|several|a couple(?: of)?|some|a little|a bit of|a pinch)\b', re.I),
     'an unstated amount: give a number', 'amount'),
    (re.compile(r'\b(?:slowly|quickly|rapidly|gently|briefly|gradually)\b', re.I),
     'a rate or duration word: give the rate or time', 'rate'),
    (re.compile(r'\b(?:room temperature|ambient temperature|overnight|until done|as needed|to taste)\b', re.I),
     'a convention a reader has to assume: define it', 'convention'),
]


def lint(text: str) -> list:
    """Warnings for vague quantities in a paper, with paper lines. Deterministic; no model. Each pattern in VAGUE
    is matched line by line outside the front matter, headings, notes and definitions; a phrase the paper defines
    (or a percentage when the paper defines its basis) is not reported."""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    terms = [(t.group(1).strip().strip('*_` ').lower(), t.group(2).lower()) for t in
             (TERM_LIST_RX.match(ln) or TERM_LINE_RX.match(ln) for ln in lines) if t]
    defined = ' '.join(f'{w} {d}' for w, d in terms)
    basis_defined = any(('percent' in w or '%' in w) or re.search(r'w/w|w/v|v/v|basis', d) for w, d in terms)
    out, in_front = [], lines[:1] == ['---']
    for i, raw in enumerate(lines, 1):
        if in_front:
            if i > 1 and raw.strip() == '---':
                in_front = False
            continue
        if TERM_LIST_RX.match(raw) or TERM_LINE_RX.match(raw) or raw.lstrip().startswith(('#', 'note ')):
            continue
        found = []
        for rx, message, kind in VAGUE:
            found += [(m.group(0).strip(), message, kind, m.start()) for m in rx.finditer(raw)]
        for phrase, message, kind, start in found:
            if kind == 'percent' and basis_defined:
                continue
            if phrase.lower() in defined or any(phrase.lower() in w for w, _d in terms):
                continue
            out.append({'line': i, 'col': start + 1, 'kind': 'vague', 'message': f'"{phrase}": {message}'})
    return out


def check_paper(text: str) -> dict:
    """S.check on the compiled program, with every diagnostic and plan row moved to the paper's lines."""
    try:
        compiled = compile_paper(text)
    except PaperError as e:
        return {'ok': False, 'errors': [e.as_dict()], 'warnings': [], 'plan': []}
    c = S.check(compiled['source'])

    def move(d):
        d = dict(d)
        if d.get('line'):
            pos = paper_line(compiled, d['line'])
            d['program_line'], d['line'] = d['line'], pos['paper_line']
            d['section'] = pos['section_title']
        return d
    plan = [move(r) for r in c.get('plan', []) if r.get('kind') not in ('use', 'let') or
            not str(r.get('label', '')).startswith(('let section_', f'let {DEFINITIONS_BINDING}', 'use'))]
    return {'ok': c['ok'], 'title': compiled['title'], 'name': compiled['title'],
            'errors': [move(e) for e in c['errors']],
            'warnings': compiled['warnings'] + lint(text) + [move(w) for w in c['warnings']], 'plan': plan,
            'terms': compiled['terms'], 'sections': compiled['sections'], 'asks': c.get('asks', 0),
            'asks_detail': [move(a) for a in c.get('asks_detail', [])], 'predictability': c.get('predictability'),
            'profile': c.get('profile')}


# ---------------------------------------------------------------------------
# Reproduction: the same paper, several disjoint cohorts
# ---------------------------------------------------------------------------

def columns_from_runs(runs: list) -> list:
    """[{'by', 'report'}] (in-process runs) -> compare columns like the host's run comparison, built from each run's
    final top-level bindings and outputs (what its fingerprint hashes)."""
    cols = []
    for r in runs:
        rows = {}
        for b in r['report'].get('bindings') or []:
            if b.get('hash'):
                rows[f'{b.get("line", 0)}:{b["name"]}'] = {'hash': b['hash'], 'value': b.get('value'),
                                                           'class': b.get('class'),
                                                           'agreement': (b.get('meta') or {}).get('agreement')}
        for o in r['report'].get('outputs') or []:
            rows[f'{o["line"]}:{o["kind"]}'] = {'hash': o['hash'], 'value': (o.get('text') or '')[:400],
                                                'class': o.get('class', 'output')}
        cols.append({'by': r['by'], 'status': r['report']['status'], 'fingerprint': r['report'].get('fingerprint'),
                     'rows': rows, 'error': (r['report'].get('error') or {}).get('message')})
    return cols


def align(compiled: dict, columns: list) -> dict:
    """Line up the cohorts' statements and map every one back to the paper. `columns` are compare columns
    ({'by', 'status', 'fingerprint', 'rows': {'LINE:NAME': {'hash', 'value', 'class'}}}).

    Agreement is judged among the cohorts that answered a statement (at least two): a cohort that failed
    (an outage, a quota) is reported under coverage, never counted as reading the paper differently.
    Three verdicts, strongest first: the whole run reproduces (every cohort finished with one fingerprint);
    the RESULTS reproduce (every finished cohort's outputs, show/return/draw, are identical); neither."""
    keys = sorted({k for c in columns for k in c['rows']}, key=lambda k: (int(k.split(':')[0]), k))
    finished = [c for c in columns if c.get('status') == 'done']
    statements = []
    model_total = model_same = 0
    for key in keys:
        line, name = key.split(':', 1)
        if name.startswith('section_') or name == DEFINITIONS_BINDING:
            continue
        answers = [(c['by'], c['rows'][key]) for c in columns if key in c['rows']]
        hashes = {}
        for by, row in answers:
            hashes.setdefault(row['hash'], []).append(by)
        cls = next((row.get('class') for _by, row in answers if row.get('class')), '')
        same = len(hashes) == 1 and len(answers) >= 2
        pos = paper_line(compiled, int(line))
        stmt = {'key': key, 'name': name, 'class': cls, 'answered': len(answers), 'of': len(columns),
                'distinct': len(hashes), 'same': same, 'comparable': len(answers) >= 2, **pos,
                'answers': [{'by': by, 'value': row.get('value'), 'hash': row['hash']} for by, row in answers]}
        if len(hashes) > 1:
            stmt['groups'] = sorted(([h, bys] for h, bys in hashes.items()), key=lambda g: (-len(g[1]), g[0]))
        if cls and cls not in ('exact', 'output') and stmt['comparable']:
            model_total += 1
            model_same += same
        statements.append(stmt)
    prints = {c.get('fingerprint') for c in finished}
    reproduces = len(finished) == len(columns) >= 2 and len(prints) == 1
    out_keys = sorted({k for c in finished for k, r in c['rows'].items() if r.get('class') == 'output'})
    results_same = len(finished) >= 2 and bool(out_keys) and all(
        all(k in c['rows'] for c in finished) and len({c['rows'][k]['hash'] for c in finished}) == 1 for k in out_keys)
    divergent = [s for s in statements if s['comparable'] and not s['same']]
    # a model statement read differently is where the paper is underspecified; a kernel result (or output)
    # that differs only follows from one of those, since the kernel computes the same thing from the same inputs
    roots = [s for s in divergent if s['class'] not in ('exact', 'output', '')]
    inherited = [s for s in divergent if s not in roots]
    return {'title': compiled['title'], 'cohorts': [{'by': c['by'], 'status': c.get('status'), 'fingerprint':
                                                     c.get('fingerprint'), 'error': c.get('error')} for c in columns],
            'coverage': {'finished': len(finished), 'of': len(columns),
                         'failed': [{'by': c['by'], 'status': c.get('status'), 'error': c.get('error')}
                                    for c in columns if c.get('status') != 'done']},
            'reproduces': reproduces, 'results_reproduce': reproduces or results_same, 'statements': statements,
            'model_statements': model_total, 'model_reproduced': model_same,
            'score': round(model_same / model_total, 4) if model_total else (1.0 if reproduces else 0.0),
            'underspecified': [{'paper_line': s['paper_line'], 'section_title': s['section_title'], 'name': s['name'],
                                'distinct': s['distinct'], 'groups': s.get('groups')} for s in roots],
            'inherited': [{'paper_line': s['paper_line'], 'name': s['name'], 'class': s['class']} for s in inherited]}


def reproduce(text: str, cohorts: list, runner) -> dict:
    """Run the paper once per cohort and align them. runner(source, by) -> {'report'}; each call must start
    from an empty record (a fresh group of agents). Cohorts are applicator specs or lists."""
    compiled = compile_paper(text)
    if len(cohorts) < 2:
        raise PaperError('reproduction needs at least two cohorts')
    runs = []
    for by in cohorts:
        res = runner(compiled['source'], by)
        runs.append({'by': by if isinstance(by, str) else ', '.join(by), 'report': res['report']})
    out = align(compiled, columns_from_runs(runs))
    out['sha256'] = compiled['sha256']
    return out


def report_text(rep: dict) -> str:
    """A plain report: does the paper reproduce, and which of its lines did the cohorts read differently."""
    verdict = ('REPRODUCES' if rep['reproduces'] else
               'RESULTS REPRODUCE (intermediate readings differ)' if rep.get('results_reproduce') else
               'does not reproduce')
    cov = rep.get('coverage') or {}
    lines = [f'{rep["title"]}: {verdict} · {rep["model_reproduced"]}/{rep["model_statements"]} model statements '
             f'identical among the cohorts that answered · {cov.get("finished", "?")}/{cov.get("of", "?")} cohorts '
             f'finished']
    for c in rep['cohorts']:
        lines.append(f'  {c["by"]:<40} {c["status"]:<8} {c.get("fingerprint") or ""}' +
                     (f'  {str(c["error"])[:160]}' if c.get('error') else ''))
    if rep.get('inherited'):
        lines.append(f'  ({len(rep["inherited"])} kernel result(s) differ only because of the lines below)')
    if rep['underspecified']:
        lines.append('Read differently (the paper is underspecified here):')
        for u in rep['underspecified']:
            groups = '; '.join(f'{len(bys)}× {h}' for h, bys in (u['groups'] or []))
            lines.append(f'  paper line {u["paper_line"]} ({u["section_title"]}): {u["name"]} — {u["distinct"]} '
                         f'different answers ({groups})')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog='python3 -m symblic.authoring.paper', description='Literate Symblic papers (.symd).')
    p.add_argument('cmd', choices=['compile', 'check', 'reproduce'])
    p.add_argument('path')
    p.add_argument('--cohort', action='append', default=[],
                   help='reproduce: an applicator (or comma-separated applicators) per cohort; at least two')
    p.add_argument('--out', default='', help='compile: write the program here')
    p.add_argument('--json', action='store_true')
    a = p.parse_args(argv)
    text = open(a.path, encoding='utf-8').read()
    if a.cmd == 'compile':
        c = compile_paper(text)
        if a.out:
            with open(a.out, 'w', encoding='utf-8') as f:
                f.write(c['source'])
        print(json.dumps(c, indent=1) if a.json else c['source'], end='' if not a.json else '\n')
        return 0
    if a.cmd == 'check':
        c = check_paper(text)
        if a.json:
            print(json.dumps(c, indent=1, default=str))
        else:
            for e in c['errors']:
                print(f'error paper line {e.get("line", 0)}: {e["message"]}')
            for w in c['warnings']:
                print(f'warning paper line {w.get("line", 0)}: {w["message"]}')
            for r in c['plan']:
                print(f'{r.get("line", 0):>4}  {"  " * r.get("depth", 0)}{r["label"]:<34} {r.get("class", "")}')
            print(f'{c.get("title")}: {"ok" if c["ok"] else "errors"} · {len(c.get("terms") or [])} terms · '
                  f'predictability {c.get("predictability")}')
        return 0 if c['ok'] else 1
    if len(a.cohort) < 2:
        print('reproduce needs at least two --cohort', file=sys.stderr)
        return 2
    import tempfile
    from symblic.providers import applicators as SA
    from symblic.kernel import run as SR
    if hasattr(SA, 'install_sigterm'):
        SA.install_sigterm()                 # a stopped run cancels its in-flight model calls

    def runner(source, by):
        apps = SA.Applicators(owner_label='operator (paper reproduce)')
        folder = tempfile.mkdtemp(prefix='symblic-paper-')
        out = sys.stderr if a.json else sys.stdout          # --json: stdout is only the JSON
        run = SR.Run(source, {}, apps, {'by': by}, folder=folder, log=lambda t: print(f'[{by}] {t}', file=out,
                                                                                      flush=True))
        rep = run.execute()
        return {'report': rep, 'trace': run.trace}
    cohorts = [c if ',' not in c else [x.strip() for x in c.split(',') if x.strip()] for c in a.cohort]
    rep = reproduce(text, cohorts, runner)
    print(json.dumps(rep, indent=1, default=str) if a.json else report_text(rep))
    return 0 if rep['reproduces'] else 1


if __name__ == '__main__':
    sys.exit(main())
