"""Context packs: a bounded, read-only summary of a few named source files, for a fresh agent task.

A coding agent that gets one small task should see only what the task needs. ``make_pack(root, names, query=...)``
reads exactly the named files under ``root`` (no directory scan, no links followed, private-looking paths and
binary files refused), and returns their hashes, their top-level symbols and, for a literal query, the lines
around each match, all within a character budget. Omissions are listed, never hidden.

Symbols come from Python's own ``ast`` module (Python files only; other languages get no symbol list). Excerpts
use the optional grep-ast package (https://github.com/Aider-AI/grep-ast) when it is installed, else plain line
context. No model, shell, recursive index or network is used.

Run it as ``python3 -m symblic.kernel.context_packs pack --root DIR --file a.py --query name`` or through
``tools/symblic-context``; ``doctor`` reports which optional packages are installed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

MAX_FILES = 24
MAX_FILE_BYTES = 256_000
MAX_TOTAL_BYTES = 1_000_000
SOURCE_EXTENSIONS = {'.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.rs',
                     '.go', '.java', '.c', '.h', '.cpp', '.cs', '.rb', '.php'}
PRIVATE_PARTS = {'node_modules', 'vendor', 'secrets', 'history', 'histories', 'logs',
                 'research_jobs', 'raw', 'backups', 'private', 'credentials'}


def selected_sources(root: Path, names: list[str]) -> list[tuple[str, bytes]]:
    """Read each explicitly named source once; never follow links or scan a tree."""
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir() or not names or len(names) > MAX_FILES:
        raise ValueError(f'Choose 1–{MAX_FILES} exact source files in a project directory')
    result = []
    total = 0
    seen = set()
    for name in names:
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts or not rel.parts:
            raise ValueError('Source filenames must stay relative to the project')
        if any(part.startswith('.') or part.casefold() in PRIVATE_PARTS
               or part.casefold().endswith('_data') or 'secret' in part.casefold()
               or 'credential' in part.casefold() for part in rel.parts):
            raise ValueError(f'Private or generated path refused: {name}')
        if rel.suffix.lower() not in SOURCE_EXTENSIONS:
            raise ValueError(f'Not an allowed source-code extension: {name}')
        cursor = root
        for part in rel.parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError(f'Symlink source refused: {name}')
        path = cursor.resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Source must be a regular file within the project')
        if str(rel) in seen:
            continue
        seen.add(str(rel))
        # O_NOFOLLOW closes the final-component race; compare inode after reading.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            data = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError(f'Source changed during reading: {name}; retry')
        total += len(data)
        if len(data) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError('Selected source exceeds the bounded context input limit')
        if b'\0' in data:
            raise ValueError(f'Binary source refused: {name}')
        data.decode('utf-8')
        result.append((rel.as_posix(), data))
    return result


def tools_status() -> dict:
    """The installed version of each optional package (None when absent)."""
    out = {}
    for package in ('grep-ast', 'tree-sitter', 'tree-sitter-language-pack'):
        try:
            out[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            out[package] = None
    return out


def _calls(node) -> list[str]:
    """The names a function or class body calls (`f(...)` and `obj.f(...)` both give `f`), at most 24."""
    names = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            target = inner.func
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return sorted(names)[:24]


def _symbols(name: str, data: bytes) -> tuple[list[dict], str, str | None]:
    """(symbols, engine, diagnostic) of one selected file's bytes, never of the file on disk again."""
    if Path(name).suffix != '.py':
        return [], 'unavailable', 'Symbols are listed for Python files only'
    tree = ast.parse(data.decode('utf-8'), filename=name)
    parents = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                parents[child] = node.name
    rows = [{'name': n.name, 'kind': 'class' if isinstance(n, ast.ClassDef) else 'function',
             'line': n.lineno, 'end_line': n.end_lineno, 'parent': parents.get(n), 'calls': _calls(n)}
            for n in ast.walk(tree)
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
    return sorted(rows, key=lambda row: row['line']), 'python-ast', None


def _excerpt(name: str, data: bytes, query: str) -> tuple[str, str, int]:
    source = data.decode('utf-8')
    lines = source.splitlines()
    matches = [i for i, line in enumerate(lines) if query.casefold() in line.casefold()]
    if not matches:
        return '', 'literal-search', 0
    # Literal search avoids regex backtracking on agent/user input.
    try:
        from grep_ast import TreeContext
        context = TreeContext(name, source, color=False, line_number=True,
                              child_context=False, margin=1, header_max=6)
        context.add_lines_of_interest(matches[:40])
        context.add_context()
        return context.format(), 'grep-ast', len(matches)
    except (ImportError, ValueError, LookupError, RuntimeError):
        selected = sorted({j for i in matches[:40] for j in range(max(0, i-2), min(len(lines), i+3))})
        return '\n'.join(f'{i+1}: {lines[i]}' for i in selected), 'line-context', len(matches)


def make_pack(root: Path, names: list[str], *, query: str = '', max_chars: int = 12000) -> dict:
    if not 1000 <= max_chars <= 48000:
        raise ValueError('max-chars must be between 1000 and 48000')
    if len(query) > 240:
        raise ValueError('Use a literal query of at most 240 characters')
    sources = selected_sources(root, names)
    remaining = max_chars
    rows = []
    omitted = []
    for name, data in sources:
        if remaining <= 0:
            omitted.append(name)
            continue
        symbols, engine, diagnostic = _symbols(name, data)
        text, search_engine, matches = _excerpt(name, data, query) if query else ('', None, 0)
        row = {'file': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
               'symbols_engine': engine, 'symbols': [], 'symbols_omitted': 0,
               'search_engine': search_engine, 'matches': matches,
               'excerpt': '', 'excerpt_truncated': False}
        if diagnostic:
            row['diagnostic'] = diagnostic
        # The budget applies to retrieved symbols/source, with manifest metadata outside it.
        for symbol in symbols:
            cost = len(json.dumps(symbol, ensure_ascii=False))
            if cost <= remaining:
                row['symbols'].append(symbol)
                remaining -= cost
            else:
                row['symbols_omitted'] += 1
        row['excerpt'] = text[:remaining]
        row['excerpt_truncated'] = len(text) > remaining
        remaining -= len(row['excerpt'])
        rows.append(row)
    return {'ok': True, 'schema': 'symblic-context/1', 'context': 'explicit-files-only',
            'query': query, 'tools': tools_status(), 'files': rows, 'omitted_files': omitted,
            'content_characters': max_chars - remaining, 'max_characters': max_chars,
            'limitations': ['Static symbols/calls are navigation evidence, not proof of runtime behavior.',
                            'Only named files were read; imports and previous conversations were not loaded.',
                            'Review selected source before sharing it with a cloud provider.']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('pack', 'doctor'))
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--file', action='append', default=[], dest='files')
    parser.add_argument('--query', default='')
    parser.add_argument('--max-chars', type=int, default=12000)
    args = parser.parse_args(argv)
    try:
        result = ({'ok': True, 'tools': tools_status(), 'python': sys.executable,
                   'install': 'python3 tools/scripts/install_symblic_tools.py'} if args.command == 'doctor'
                  else make_pack(args.root, args.files, query=args.query, max_chars=args.max_chars))
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
