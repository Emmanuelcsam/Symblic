"""Inventory every documentation fence; execute only declared, pinned safe cases.

    python3 tools/scripts/symblic_docs_audit.py inventory --root docs/reference [--output FILE]
    python3 tools/scripts/symblic_docs_audit.py verify --root docs/reference --inventory FILE
    python3 tools/scripts/symblic_docs_audit.py check --root docs/reference --manifest CASES.json --runtime-root .

Inventory needs markdown-it-py 3.0.0 (https://github.com/executablebooks/markdown-it-py), the CommonMark
parser, installed for the interpreter that runs this script. Native checks use a fresh Python child
(RUNTIME_ROOT/.venv/bin/python when it exists), closed syntax/call allowlists, refusing hosts, no run folder,
and fixed resource limits. Shell/Python/JS fences are never executed. Unknown examples remain unknown, not
passing conformance. docs/reference/documentation-cases.json is the pinned case manifest the original
project used (see docs/reference/DOCUMENTATION-CONFORMANCE.md); its fence pins refer to the documents as
they were then, so re-pin it after editing them.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = 1
PARSER_VERSION = '3.0.0'
MAX_FILES = 2048
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 32_000_000
MAX_FENCES = 8192
MAX_CANDIDATES = 32768
MAX_SOURCE_BYTES = 8192
MAX_CASES = 32
MAX_JSON_BYTES = 8_000_000
_DELIMITER = re.compile(r'`{3,}|~{3,}')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
SAFE_CALLS = frozenset({'len', 'words', 'contains', 'quadratic_minimize', 'quadratic_verify',
                        'reconcile', 'quantity_measure', 'quantity_convert', 'quantity_exact',
                        'quantity_compare', 'quantity_div', 'proof_parse', 'proof_check',
                        'finite_parse', 'finite_check', 'ising_minimize', 'ising_energy'})
SAFE_NODES = frozenset({'program', 'use', 'let', 'assert', 'show', 'num', 'lit', 'str',
                        'name', 'list', 'record', 'set', 'bin', 'cmp', 'un', 'quant',
                        'attr', 'index', 'call', 'range', 'cond'})


def fail(code):
    raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _json(raw):
    if len(raw) > MAX_JSON_BYTES:
        fail('json_bound')
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                fail('duplicate_key')
            result[key] = value
        return result
    def approximate(_):
        fail('json_number')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_float=approximate,
                          parse_constant=approximate)
    except (UnicodeError, RecursionError, json.JSONDecodeError):
        fail('invalid_json')


def _read(path, maximum):
    if path.is_symlink() or not path.is_file():
        fail('regular_file_required')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        fail('file_bound')
    return raw


def parser():
    if importlib.metadata.version('markdown-it-py') != PARSER_VERSION:
        fail('parser_version')
    from markdown_it import MarkdownIt
    from markdown_it.rules_block.fence import fence
    def marked_fence(state, start, end, silent):
        accepted = fence(state, start, end, silent)
        if accepted and not silent:
            token = state.tokens[-1]
            last = token.map[1] - 1
            pos = state.bMarks[last] + state.tShift[last]
            tail = state.src[pos:state.eMarks[last]]
            closing = re.fullmatch(re.escape(token.markup[0]) + '{' + str(len(token.markup)) + ',}[ \t]*', tail)
            token.meta['explicitly_closed'] = last > start and bool(closing)
        return accepted
    result = MarkdownIt('commonmark', {'maxNesting': 64})
    # Preserve the stock rule's paragraph/list terminator contexts. Dropping
    # these silently hides fenced blocks nested after list-item prose.
    result.block.ruler.at('fence', marked_fence,
                         {'alt': ['paragraph', 'reference', 'blockquote', 'list']})
    return result


def _classification(language, closed):
    if not closed:
        return 'unknown_unclosed', 'manual_review'
    if language in ('sh', 'bash', 'zsh', 'shell', 'console', 'powershell'):
        return 'shell', 'never_execute'
    if language in ('text', 'plaintext', 'markdown', 'md'):
        return 'prose', 'not_an_execution_contract'
    if language in ('pseudocode', 'proposal', 'symblic-proposal'):
        return 'proposal', 'not_executed'
    return 'unknown', 'manual_review'


def scan_text(text, path, *, include_content=False):
    """CommonMark fences plus every lexical delimiter run, including literals."""
    if type(text) is not str or len(text.encode('utf-8')) > MAX_FILE_BYTES:
        fail('text_bound')
    lines = text.splitlines(keepends=True)
    if len(lines) > 100000:
        fail('line_bound')
    fences = []
    for token in parser().parse(text):
        if token.type != 'fence':
            continue
        if len(fences) >= MAX_FENCES:
            fail('fence_bound')
        start, stop = token.map
        closed = token.meta['explicitly_closed']
        info = token.info.strip()
        language = info.split()[0].lower() if info else ''
        classification, status = _classification(language, closed)
        raw_content = ''.join(lines[start + 1:stop - int(closed)])
        row = {'id': f'{path}#fence-{len(fences) + 1}', 'path': path,
               'ordinal': len(fences) + 1, 'opening_line': start + 1,
               'content_start_line': start + 2, 'end_line': stop,
               'closing_line': stop if closed else None, 'closed': closed,
               'marker': token.markup, 'info': info, 'language': language,
               'content_sha256': sha(raw_content.encode('utf-8')),
               'normalized_content_sha256': sha(token.content.encode('utf-8')),
               'raw_content_bytes': len(raw_content.encode('utf-8')),
               'classification': classification, 'status': status}
        if include_content:
            row['_content'] = token.content
        fences.append(row)
    candidates = []
    at = 0
    for number, line in enumerate(lines, 1):
        while at < len(fences) and fences[at]['end_line'] < number:
            at += 1
        owner = fences[at] if at < len(fences) and fences[at]['opening_line'] <= number else None
        for match in _DELIMITER.finditer(line):
            if len(candidates) >= MAX_CANDIDATES:
                fail('delimiter_bound')
            if owner:
                role = 'opening' if number == owner['opening_line'] else (
                    'closing' if number == owner['closing_line'] else 'literal_fence_content')
            else:
                role = 'non_fence_or_manual_review'
            candidates.append({'line': number, 'column': match.start() + 1,
                               'marker': match.group(), 'role': role,
                               'fence_id': owner['id'] if owner else None})
    return fences, candidates


def _files(root):
    if root.is_symlink() or not root.is_dir():
        fail('directory_required')
    found = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        if len(Path(directory).relative_to(root).parts) > 16:
            fail('directory_depth')
        for name in sorted(dirs + files):
            path = Path(directory) / name
            if path.is_symlink():
                fail('symlink_refused')
            if name in files:
                if not stat.S_ISREG(path.stat().st_mode):
                    fail('regular_file_required')
                found.append(path)
                if len(found) > MAX_FILES:
                    fail('file_count_bound')
    return sorted(found)


def inventory(root, *, include_content=False):
    root = Path(root)
    rows, fences, candidates, total = [], [], [], 0
    for path in _files(root):
        raw = _read(path, MAX_FILE_BYTES)
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            fail('total_byte_bound')
        relative = path.relative_to(root).as_posix()
        record = {'path': relative, 'bytes': len(raw), 'sha256': sha(raw)}
        try:
            if b'\0' in raw:
                raise UnicodeError()
            text = raw.decode('utf-8')
        except UnicodeError:
            record.update(status='binary_not_markdown', fences=0)
        else:
            found, lexical = scan_text(text, relative, include_content=include_content)
            if len(fences) + len(found) > MAX_FENCES:
                fail('fence_bound')
            fences.extend(found)
            candidates.extend({'path': relative, **row} for row in lexical)
            if len(candidates) > MAX_CANDIDATES:
                fail('delimiter_bound')
            record.update(status='text_scanned', fences=len(found))
        rows.append(record)
    public_fences = [{k: v for k, v in row.items() if k != '_content'} for row in fences]
    core = {'schema': 'symblic.docs.inventory.v1', 'version': VERSION,
            'parser': {'name': 'markdown-it-py', 'version': PARSER_VERSION,
                       'preset': 'commonmark', 'max_nesting': 64},
            'scope': 'All regular files below the supplied documentation root; UTF-8 non-NUL text scanned. Binary files hashed and listed.',
            'files': rows, 'fences': public_fences, 'delimiter_candidates': candidates,
            'coverage': {'files': len(rows), 'bytes': total, 'commonmark_fences': len(fences),
                         'lexical_delimiter_runs': len(candidates),
                         'non_fence_candidates_for_review': sum(c['fence_id'] is None for c in candidates),
                         'unaccounted_delimiter_runs': 0,
                         'unclosed_fences': sum(not row['closed'] for row in fences)},
            'limits': ['CommonMark-parser fence inventory with maximum container nesting 64; every lexical delimiter run is separately accounted for. This is not a claim that all examples conform.',
                       'Delimiter runs outside parsed fences remain visible; inline mentions and indented/HTML code may be intentional.',
                       'Unknown and unclosed fences require review. No automatic document execution.']}
    core['sha256'] = sha(canonical(core))
    return (core, fences) if include_content else core


def verify_inventory(root, saved):
    if type(saved) is not dict or saved.get('schema') != 'symblic.docs.inventory.v1':
        fail('inventory_schema')
    recorded = dict(saved)
    pinned = recorded.pop('sha256', None)
    if pinned != sha(canonical(recorded)):
        fail('inventory_hash')
    current = inventory(root)
    previous_files = {row['path']: row['sha256'] for row in saved['files']}
    current_files = {row['path']: row['sha256'] for row in current['files']}
    changed = sorted(name for name in previous_files.keys() | current_files.keys()
                     if previous_files.get(name) != current_files.get(name))
    return {'ok': current['sha256'] == pinned, 'changed_paths': changed,
            'previous_sha256': pinned, 'current_sha256': current['sha256'],
            'scope': 'Exact inventory and whole-file drift; no examples executed.'}


def _manifest(value):
    if type(value) is not dict or set(value) != {'schema', 'cases'} or value['schema'] != 'symblic.docs.cases.v1':
        fail('manifest_schema')
    if type(value['cases']) is not list or not 1 <= len(value['cases']) <= MAX_CASES:
        fail('case_bound')
    seen = set()
    for row in value['cases']:
        if type(row) is not dict or set(row) != {'id', 'fence_id', 'content_sha256', 'action', 'expected_status', 'expected_error_kind'}:
            fail('case_schema')
        if type(row['id']) is not str or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', row['id']) or row['id'] in seen:
            fail('case_id')
        seen.add(row['id'])
        if type(row['fence_id']) is not str or len(row['fence_id']) > 512:
            fail('fence_id')
        if type(row['content_sha256']) is not str or not _SHA.fullmatch(row['content_sha256']):
            fail('content_hash')
        if row['action'] not in ('execute', 'check'):
            fail('case_action')
        allowed = ('done', 'failed') if row['action'] == 'execute' else ('check_passed', 'check_refused')
        if row['expected_status'] not in allowed:
            fail('expected_status')
        if row['expected_error_kind'] is not None and row['expected_error_kind'] not in ('syntax', 'type', 'check', 'runtime', 'name', 'budget'):
            fail('expected_error_kind')
    return value


def _safe_ast(program, S):
    todo = [(program['statements'], 0)]
    count = 0
    while todo:
        value, depth = todo.pop()
        count += 1
        if count > 4000 or depth > 64:
            fail('ast_bound')
        if isinstance(value, S.Node):
            if value.k not in SAFE_NODES:
                fail('unsafe_node')
            if value.k == 'call' and value.fn not in SAFE_CALLS:
                fail('unsafe_call')
            if value.k == 'use' and (set(value.options) != {'profile'} or
                    value.options['profile'].k != 'name' or value.options['profile'].name != 'verified'):
                fail('unsafe_use')
            if value.k == 'assert' and value.on_fail != 'fail':
                fail('unsafe_retry')
            todo.extend((v, depth + 1) for v in value.__dict__.values())
        elif type(value) in (list, tuple):
            todo.extend((v, depth + 1) for v in value)
        elif type(value) is dict:
            todo.extend((v, depth + 1) for v in value.values())


def native_case(source, action):
    """Inert in-process entry used only inside the capped fresh worker/tests."""
    if type(source) is not str or len(source.encode('utf-8')) > MAX_SOURCE_BYTES or action not in ('execute', 'check'):
        fail('native_input')
    from unittest.mock import patch

    from symblic.kernel import language as S
    from symblic.kernel import execution_pins as X
    from symblic.kernel import run as SR
    class Refuse:
        calls = 0
        def call(self, *_args, **_kwargs):
            self.calls += 1
            raise RuntimeError('documentation_model_refused')
        delegate = call
        perform = call
        def catalogue(self):
            return {}
    apps, effects = Refuse(), Refuse()
    def deny(*_args, **_kwargs):
        raise RuntimeError('documentation_external_operation_refused')
    with patch('socket.create_connection', deny), patch('socket.socket.connect', deny), \
            patch('subprocess.Popen', deny), patch('os.system', deny):
        X._check_loaded_runtime()
        if action == 'check':
            checked = S.check(source)
            result = {'status': 'check_passed' if checked['ok'] else 'check_refused',
                      'error_kind': checked['errors'][0].get('kind') if checked.get('errors') else None,
                      'outputs': [], 'calls': 0, 'checks': 0}
        else:
            try:
                program = S.parse(source)
                _safe_ast(program, S)
            except ValueError:
                return {'status': 'refused', 'error_kind': 'unsafe_syntax', 'outputs': [],
                        'calls': 0, 'applicator_calls': 0, 'effect_calls': 0, 'store_folder': None}
            except S.SymblicError as error:
                return {'status': 'failed', 'error_kind': error.kind, 'outputs': [],
                        'calls': 0, 'applicator_calls': 0, 'effect_calls': 0, 'store_folder': None}
            run = SR.Run(source, applicators=apps, folder=None,
                         options={'by': 'fixture:refuse', 'max_calls': 0, 'max_steps': 20000,
                                  'parallel': 1, 'side_effects': False, 'effects': effects,
                                  'determine': False, 'solve': False, 'constructor': 'off',
                                  'execution_profile': 'verified'})
            report = run.execute()
            result = {'status': report['status'], 'error_kind': (report.get('error') or {}).get('kind'),
                      'outputs': [{'kind': row['kind'], 'canonical': row.get('canonical'),
                                   'hash': row['hash']} for row in report['outputs']],
                      'calls': report['calls'], 'checks': len(run.checks)}
            if run.store.dir is not None:
                fail('store_created')
        X._check_loaded_runtime()
        result.update(applicator_calls=apps.calls, effect_calls=effects.calls, store_folder=None,
                      kernel=S.kernel_id(), runtime_sources=dict(X._RUNTIME))
    return result


def _worker(runtime_root):
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    sys.path.insert(0, str(Path(runtime_root).resolve(strict=True)))
    data = _json(sys.stdin.buffer.read(MAX_SOURCE_BYTES * 6 + 1024))
    if type(data) is not dict or set(data) != {'source', 'action'}:
        fail('worker_schema')
    print(json.dumps(native_case(data['source'], data['action']), sort_keys=True))


def run_cases(root, manifest, runtime_root):
    manifest = _manifest(manifest)
    audit, rows = inventory(root, include_content=True)
    by_id = {row['id']: row for row in rows}
    selected = []
    for case in manifest['cases']:
        row = by_id.get(case['fence_id'])
        if not row or row['content_sha256'] != case['content_sha256']:
            fail('fence_pin_drift')
        if not row['closed'] or row['language'] not in ('sym', 'symblic'):
            fail('unsupported_case_fence')
        if len(row['_content'].encode('utf-8')) > MAX_SOURCE_BYTES:
            fail('source_bound')
        selected.append((case, row))
    runtime_root = Path(runtime_root).resolve(strict=True)
    python = runtime_root / '.venv/bin/python'
    if not python.is_file():
        python = Path(sys.executable)
    outcomes = []
    for case, row in selected:
        with tempfile.TemporaryDirectory(prefix='symblic-doc-case-') as tmp:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            env.pop('PYTHONPATH', None)
            try:
                child = subprocess.run([str(python), str(Path(__file__).resolve()), '_worker', str(runtime_root)],
                    input=canonical({'source': row['_content'], 'action': case['action']}),
                    capture_output=True, timeout=20, cwd=tmp, env=env, check=False)
            except subprocess.TimeoutExpired:
                observed = {'status': 'worker_timeout', 'error_kind': None}
            else:
                observed = _json(child.stdout) if child.returncode == 0 and len(child.stdout) <= 1_000_000 else {
                    'status': 'worker_failed', 'error_kind': None, 'returncode': child.returncode}
            artifacts = [p.relative_to(tmp).as_posix() for p in Path(tmp).rglob('*')]
            if artifacts:
                observed = {'status': 'unexpected_temp_artifact', 'error_kind': None}
        matched = observed['status'] == case['expected_status'] and observed.get('error_kind') == case['expected_error_kind']
        matched = matched and observed.get('calls', 0) == 0 and observed.get('applicator_calls', 0) == 0 and observed.get('effect_calls', 0) == 0
        outcomes.append({'id': case['id'], 'fence_id': row['id'], 'content_sha256': row['content_sha256'],
                         'classification': 'expected-failure' if case['expected_status'] in ('failed', 'check_refused') else 'executable',
                         'action': case['action'], 'expected_status': case['expected_status'],
                         'expected_error_kind': case['expected_error_kind'], 'matched': matched,
                         'observed': observed})
    return {'schema': 'symblic.docs.conformance.v1', 'inventory_sha256': audit['sha256'],
            'manifest_sha256': sha(canonical(manifest)), 'driver_sha256': sha(Path(__file__).read_bytes()),
            'cases': outcomes, 'ok': all(row['matched'] for row in outcomes),
            'uncontracted_fence_count': len(rows) - len({case['fence_id'] for case in manifest['cases']}),
            'scope': 'Only the explicitly declared pinned cases were checked. All other fences remain unassessed; no providers, effects, durable stores or shell fences executed.'}


def _save(path, value):
    raw = canonical(value)
    if len(raw) > MAX_JSON_BYTES:
        fail('output_bound')
    if path:
        with Path(path).open('xb') as stream:
            stream.write(raw + b'\n')
    else:
        print(raw.decode('utf-8'))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['_worker']:
        if len(argv) != 2:
            fail('worker_arguments')
        _worker(argv[1])
        return 0
    args = argparse.ArgumentParser(description=__doc__)
    sub = args.add_subparsers(dest='command', required=True)
    for name in ('inventory', 'verify', 'check'):
        command = sub.add_parser(name)
        command.add_argument('--root', required=True, help='Documentation tree to read')
        command.add_argument('--output', help='Create a new receipt file; never overwrite')
        if name == 'verify':
            command.add_argument('--inventory', required=True)
        if name == 'check':
            command.add_argument('--manifest', required=True)
            command.add_argument('--runtime-root', required=True, help='Existing native runtime checkout')
    parsed = args.parse_args(argv)
    try:
        if parsed.command == 'inventory':
            result = inventory(parsed.root)
        elif parsed.command == 'verify':
            result = verify_inventory(parsed.root, _json(_read(Path(parsed.inventory), MAX_JSON_BYTES)))
        else:
            result = run_cases(parsed.root, _json(_read(Path(parsed.manifest), 65536)), parsed.runtime_root)
        _save(parsed.output, result)
        return 0 if result.get('ok', True) else 1
    except (ValueError, OSError, importlib.metadata.PackageNotFoundError) as error:
        message = str(error)
        code = message if re.fullmatch(r'[a-z_]{1,64}', message) else 'audit_refused'
        print(json.dumps({'ok': False, 'error': code}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
