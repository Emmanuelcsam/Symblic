"""Deterministic repair of a small model's JavaScript answer for one named unit, done by code, never by a model.

Used when a program asks for one unit of a larger file (`ask f: Code js unit NAME reusing A, B`). A 0.5B to 1B
model fails such a unit for mechanical reasons far more often than for reasoning ones: it volunteers a copy of
a helper the file already holds (the kernel refuses a second declaration), it drops the `function` keyword, it
splits its answer over several fences, it declares its own unit twice, or it reassigns a helper with a bare
`helper = function ...` that js_test's protected bindings swallow silently while the assembled page would run
it. Each of those is repaired here, and only when the program asked for it: the fenced block that declares the
unit is the one taken, a missing keyword in front of the unit's own declaration is restored, the candidate's
top-level declarations of and bare assignments to reused names are cut out, the unit's own bare assignment
becomes a `const`, and a unit declared twice keeps its `function` form.

Parsing is the pinned Acorn (acorn.js) in a local node process running normalize.js (parse only, never
executed); its offsets are UTF-16 code units, so every cut is made on the UTF-16 form of the text. The
normalized text is the answer: the tests run on it and the file is assembled from it, so what passed is what
ships. Anything else stays exactly as the model wrote it, and text that does not parse is left alone for the
tests to report.

VERSION and the hashes of this file, normalize.js and acorn.js are part of the kernel identity
(symblic.kernel.language.kernel_id): a change here is a change of the kernel.

Depends on: symblic.js.check (node discovery), symblic.js.contract (the pinned parser hash). Used by:
symblic.kernel.language.read_answer for `Code js unit ... reusing ...` answers.
"""
from __future__ import annotations

# Import identity must precede first-party circular imports.
_symblic_identity = __import__('importlib').import_module('symblic.kernel.identity')
_symblic_import_identity = _symblic_identity.record(__file__, __import__('sys')._getframe().f_code)

import hashlib
import json
import os
import re
import subprocess

VERSION = 2                  # part of kernel_id: a behaviour change here is a kernel change
_FENCE = re.compile(r'```[ \t]*([A-Za-z0-9_+.-]*)[ \t]*\n(.*?)(?:\n[ \t]*```|\Z)', re.S)
_OPEN_FENCE = re.compile(r'(?m)^[ \t]*```[A-Za-z0-9_+-]*[ \t]*\n')
_NAME = re.compile(r'[A-Za-z_$][\w$]*')
MAX_SOURCE = 400_000
WALL_SECONDS = 20
HERE = os.path.dirname(os.path.abspath(__file__))
PARSER = os.path.join(HERE, 'acorn.js')          # pinned Acorn 8.8.1, shared with check.py and contract.py
RUNNER = os.path.join(HERE, 'normalize.js')      # parse-only node script: top-level declarations and their ranges
_checked: dict = {}


def _decl_line(name: str) -> re.Pattern:
    """One line that declares `name`: a keyword form, `name = function/arrow`, or `name(args) {` with the keyword
    dropped. A call such as `name('a')` is not a declaration. Lines are short, so this cannot run away."""
    n = re.escape(name)
    return re.compile(rf'^(?:(?:async\s+)?function\s*\*?\s*{n}\s*\(|(?:const|let|var)\s+{n}\s*=|class\s+{n}(?![\w$])'
                      rf'|{n}\s*=\s*(?:async\b|function\b|\(|[A-Za-z_$][\w$]*\s*=>)|{n}\s*\([^)]*\)\s*\{{)')


def _declares(code: str, name: str) -> bool:
    pat = _decl_line(name)
    return any(pat.match(line.lstrip()) for line in code.split('\n'))


def _mentions(code: str, name: str) -> bool:
    return re.search(rf'(?<![\w$]){re.escape(name)}(?![\w$])', code) is not None


def choose_block(reply: str, names: list[str]) -> str:
    """The fenced block that declares one of `names` (the last such), else the kernel's rule: the last block, else a
    JSON object's "answer", else the whole reply."""
    s = str(reply or '').replace('\r\n', '\n').replace('\r', '\n')
    blocks = [b[1] for b in _FENCE.findall(s)]
    for block in reversed(blocks):
        if any(_declares(block, n) for n in names):
            return block
    if blocks:
        return blocks[-1]
    # an opening fence that was never closed (a 0.5B model wrote the unit, kept going and hit its token
    # limit, 2026-10-11): the text after the last opening fence is the block; the junk cut trims its tail
    opened = list(_OPEN_FENCE.finditer(s))
    if opened:
        tail = s[opened[-1].end():]
        if any(_declares(tail, n) for n in names):
            return tail
    stripped = s.strip()
    if stripped.startswith('{') and stripped.endswith('}'):
        try:
            obj = json.loads(stripped)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get('answer'), str):
            return obj['answer']
    return stripped


_POS = re.compile(r'\((\d+):(\d+)\)\s*$')


def cut_trailing_junk(code: str, names: list[str], *, node: str | None = None) -> str:
    """A small model often continues past the unit it was asked for: the same constants declared again, renamed
    copies, then broken text such as `function f()() {` (gemma3:1b, 2026-10-11, up to its token limit). The lines
    from the first REAL syntax error onward are dropped, repeatedly, as long as every unit name is still declared in
    what remains. A redeclaration of a unit name is hidden behind a placeholder while the rest is parsed (the
    llama3.2:1b `const f = ...` and `function f` pair is drop_own_duplicates' business, not junk). When real junk
    was cut, a redeclaration of a unit name that came AFTER every unit name was already declared marks where the
    junk began, and the block is cut there too (the 0.5B reply: the unit, then `function SHAPES_I()`, then
    `function SHAPES(...)` again). A block that parses, or one whose cut would lose a unit name, is unchanged."""
    current = code
    hidden = []                       # (marker, name, line number of the hidden redeclaration)
    cut = False
    for _ in range(32):
        out = _parse(current, names, node=node)
        if not out or 'error' not in out:
            break
        error = str(out.get('error') or '')
        dup = _DUPLICATE.search(error)
        if dup and dup.group(1) in names:
            name, pos = dup.group(1), _offset16(current, int(dup.group(2)), int(dup.group(3)))
            units = current.encode('utf-16-le', 'surrogatepass')
            if units[pos * 2:pos * 2 + len(name) * 2].decode('utf-16-le', errors='replace') != name:
                return code
            marker = f'{_PLACEHOLDER}{len(hidden)}_'
            hidden.append((marker, name, int(dup.group(2))))
            current = _edit(current, [(pos, pos + len(name), marker)])
            continue
        m = _POS.search(error)
        if not m:
            return code
        line = int(m.group(1))
        lines = current.split('\n')
        if line < 1 or line > len(lines):
            return code
        candidate = '\n'.join(lines[:line - 1]).rstrip()
        restored = candidate
        for marker, name, _ln in hidden:
            restored = restored.replace(marker, name)
        if not candidate or not all(_declares(restored, n) for n in names):
            return code
        current = candidate
        cut = True
    if cut and hidden:
        # the junk began where a unit name was declared again after all of them already were
        first = min(ln for _m, _n, ln in hidden)
        lines = current.split('\n')
        candidate = '\n'.join(lines[:first - 1]).rstrip()
        restored = candidate
        for marker, name, _ln in hidden:
            restored = restored.replace(marker, name)
        if candidate and all(_declares(restored, n) for n in names):
            parsed = _parse(restored, names, node=node)
            if parsed and 'error' not in parsed:
                return restored
    for marker, name, _ln in hidden:
        current = current.replace(marker, name)
    return current


def restore_keyword(code: str, names: list[str]) -> str:
    """`inline(s) { ... }` at the top of an answer is the unit with its `function` dropped (llama3.2:1b, 2026-10-10)."""
    stripped = code.lstrip()
    for name in names:
        if re.match(rf'{re.escape(name)}\s*\([^)]*\)\s*\{{', stripped):
            return 'function ' + stripped
    return code


def parser_ok() -> bool:
    """The vendored Acorn is used only when its bytes match the pinned hash (symblic.js.contract.PARSER_SHA256)."""
    if 'parser' not in _checked:
        ok = False
        try:
            from symblic.js import contract as JC
            with open(PARSER, 'rb') as fh:
                ok = hashlib.sha256(fh.read()).hexdigest() == JC.PARSER_SHA256
        except (ImportError, OSError, AttributeError):
            ok = False
        _checked['parser'] = ok
    return _checked['parser']


def _parse(code: str, names: list[str] | None, *, node: str | None = None) -> dict | None:
    """The parser's answer: {'declarations': [...]} or {'error': text}; None when node or the parser is unavailable."""
    if len(code) > MAX_SOURCE:
        return None
    node = node or _node()
    if not node or not parser_ok():
        return None
    body = json.dumps({'source': code, 'names': list(names) if names is not None else None})
    try:
        proc = subprocess.run([node, RUNNER, PARSER], input=body, capture_output=True, text=True, timeout=WALL_SECONDS)
        out = json.loads(proc.stdout or '{}')
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return out if isinstance(out, dict) else None


def declarations(code: str, names: list[str] | None = None, *, node: str | None = None) -> list[dict] | None:
    """Top-level declarations and bare assignments of `code` (all, or only those binding `names`) with UTF-16 source
    ranges; None when the parser is unavailable or the code does not parse."""
    out = _parse(code, names, node=node)
    if not out or 'declarations' not in out:
        return None
    return [d for d in out['declarations'] if isinstance(d, dict) and isinstance(d.get('start'), int) and isinstance(d.get('end'), int)]


def _edit(code: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply (start, end, replacement) edits given in UTF-16 code units (Acorn's offsets), later ones first. A cut
    takes the line break that followed it; when it would glue two lines, a line break stays."""
    units = code.encode('utf-16-le', 'surrogatepass')
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        a, b = start * 2, end * 2
        if not 0 <= a <= b <= len(units) or (a == b and repl == ''):
            continue
        if repl == '':
            if units[b:b + 2] == b'\n\x00':
                b += 2
            elif a > 0 and units[a - 2:a] != b'\n\x00':
                repl = '\n'
        units = units[:a] + repl.encode('utf-16-le', 'surrogatepass') + units[b:]
    return units.decode('utf-16-le', errors='surrogatepass').strip('\n')


def drop_reused(code: str, given: list[str], *, node: str | None = None) -> str:
    """`code` without its top-level declarations of `given` names (copies of helpers earlier units already tested) nor
    its bare assignments to them (a reassignment the sandbox swallows but the assembled page would run)."""
    given = [g for g in given if _NAME.fullmatch(g) and _mentions(code, g)]
    if not given:
        return code
    found = declarations(code, given, node=node)
    if not found:
        return code
    return _edit(code, [(d['start'], d['end'], '') for d in found])


def declare_own(code: str, names: list[str], *, node: str | None = None) -> str:
    """A unit written as a bare assignment (`escapeHtml = function (s) {...}`, llama3.2:1b) becomes a `const`
    declaration: the page then has a real binding and a second copy is a visible duplicate, not a silent overwrite.
    An assignment to a unit name that the answer also declares is cut (the declaration wins)."""
    if not any(re.search(rf'(?m)^[ \t]*{re.escape(n)}[ \t]*=', code) for n in names):
        return code
    found = declarations(code, None, node=node)
    if not found:
        return code
    declared = {d['name'] for d in found if d.get('kind') != 'assign'}
    edits = []
    for d in found:
        if d.get('kind') == 'assign' and d.get('name') in names:
            edits.append((d['start'], d['end'], '') if d['name'] in declared else (d['start'], d['start'], 'const '))
            declared.add(d['name'])          # a second bare assignment of the same name is then a cut
    return _edit(code, edits) if edits else code


_DUPLICATE = re.compile(r"Identifier '([\w$]+)' has already been declared \((\d+):(\d+)\)")
_PLACEHOLDER = '__symblic_duplicate__'


def _offset16(code: str, line: int, col: int) -> int:
    """Acorn's (line, column) as a UTF-16 offset."""
    lines = code.split('\n')
    return sum(len(l.encode('utf-16-le', 'surrogatepass')) // 2 + 1 for l in lines[:line - 1]) + col


def drop_own_duplicates(code: str, names: list[str], *, node: str | None = None) -> str:
    """`code` with one declaration per unit name: llama3.2:1b answered `const isUlBlock = ...` AND
    `function isUlBlock ...` (2026-10-10), which a script cannot declare twice (Acorn refuses to parse it). The second
    declaration is renamed to a placeholder so the text parses, the declarations are listed, the `function` one is
    kept when there is one (the form the unit asked for), else the first, and the other is cut. Two plain `function`
    declarations parse, so they are left as JavaScript runs them (the last wins)."""
    for _ in range(8):
        out = _parse(code, None, node=node)
        m = _DUPLICATE.search(str((out or {}).get('error') or ''))
        if not m or m.group(1) not in names:
            return code
        name, pos = m.group(1), _offset16(code, int(m.group(2)), int(m.group(3)))
        units = code.encode('utf-16-le', 'surrogatepass')
        if units[pos * 2:pos * 2 + len(name) * 2].decode('utf-16-le', errors='replace') != name:
            return code
        tmp = _edit(code, [(pos, pos + len(name), _PLACEHOLDER)])
        found = declarations(tmp, None, node=node)
        mine = [d for d in (found or []) if d.get('name') in (name, _PLACEHOLDER)]
        if len(mine) < 2:
            return code
        keep = next((d for d in mine if d.get('kind') == 'function'), mine[0])
        text = _edit(tmp, [(d['start'], d['end'], '') for d in mine if d is not keep])
        code = text.replace(_PLACEHOLDER, name)
    return code


def normalize(reply: str, ty: dict, *, node: str | None = None) -> str:
    """The Code js answer for a unit type with `names` (and maybe `given`); '' when the type names no unit."""
    names = [n for n in (ty.get('names') or []) if isinstance(n, str) and _NAME.fullmatch(n)]
    if not names:
        return ''
    if len(str(reply or '')) > MAX_SOURCE:                   # bounded before any scan; the kernel's coerce refuses it
        return str(reply or '')[:MAX_SOURCE]
    code = cut_trailing_junk(restore_keyword(choose_block(reply, names), names), names, node=node)
    given = [g for g in (ty.get('given') or []) if isinstance(g, str) and g not in names]
    code = declare_own(drop_reused(code, given, node=node), names, node=node)
    return drop_own_duplicates(code, names, node=node)


def asset_hashes() -> dict:
    out = {}
    for name, path in (('normalize.py', __file__), ('normalize.js', RUNNER), ('acorn.js', PARSER)):
        try:
            with open(path, 'rb') as fh:
                out[name] = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            out[name] = None
    return out


def _node() -> str | None:
    try:
        from symblic.js import check as symblic_js
        return symblic_js.node_path()
    except Exception:  # noqa: BLE001
        return None
