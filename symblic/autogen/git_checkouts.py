"""Own git checkouts for autogen attempts, and bringing an accepted attempt home.

What it is for
    An autogen attempt never writes into the project folder. It works in its own git checkout
    beside the project; only an attempt that code accepted is applied to the project, and only
    where that is safe. The kernel lane (symblic/autogen/kernel_lane.py) uses these helpers for
    every spec-sheet build; a TaskRunner may use them for agent attempts too.

The three operations
    make_checkout(project_dir, name)
        A git worktree at <project top>.autogen/<name>-<YYYYmmdd-HHMMSS> on a new branch
        autogen/<name>-<YYYYmmdd-HHMMSS>, started from the project's HEAD. The project's
        uncommitted work (tracked changes and untracked, not ignored files under 25 MB, caches
        skipped) is carried over as the branch's first commit, the "baseline", so the attempt
        starts from exactly what the operator sees and its own changes are what follows the
        baseline. A checkout this name already made (a crash before it was recorded) is adopted
        instead of made twice. The project folder itself is never modified.
    commit_all(checkout, message)
        Stage and commit everything in the checkout.
    apply_to_project(checkout)
        Apply the checkout's committed changes since its baseline to the project's working tree,
        file by file: a file is written (or deleted) only where the project still holds the
        baseline version, or where git merge-file combines both sides without an overlap. Any
        clash refuses the whole apply ("Nothing was applied: N file(s) clash with your
        checkout: ..."), so a half-applied result never happens. Nothing is committed in the
        project. Applying the same checkout twice changes nothing the second time.

Records
    A checkout is described by a dict: worktree (its folder), cwd (the project folder's
    counterpart inside it), branch, base_sha (the baseline commit), base_branch, main_root (the
    project repository's top folder), carried (what was carried over, or None) and adopted.

Depends on
    The git command line (2.25 or newer) and the Python standard library. Git runs with a
    minimal environment (PATH, HOME, LANG; no pager, no prompts), so a caller's secrets in its
    environment never reach it.

Nothing here prunes old checkouts: they are evidence, and removing them is the operator's call
(`git worktree remove <folder>` and `git branch -D <branch>`).
"""
from __future__ import annotations

import datetime
import glob
import os
import re
import shutil
import subprocess
import tempfile

BRANCH_PREFIX = 'autogen/'
FOLDER_SUFFIX = '.autogen'
STAMP_FORMAT = '%Y%m%d-%H%M%S'
STAMP_RX = re.compile(r'^\d{8}-\d{6}$')
BRANCH_RX = re.compile(r'^autogen/[\w.-]+$')
NAME_RX = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$')
CARRY_MAX_BYTES = 25 * 1024 * 1024      # an untracked file larger than this stays behind
GIT_TIMEOUT = 900                       # seconds; a busy machine makes worktree operations slow
JUNK = re.compile(r'(^|/)(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|node_modules|\.cache)(/|$)'
                  r'|\.pyc$|\.swp$|(^|/)\.DS_Store$')
IDENTITY = ('-c', 'user.name=autogen', '-c', 'user.email=autogen@localhost')


class CheckoutError(RuntimeError):
    """A refusal; the message says what is wrong and what to do."""


def _env() -> dict:
    return {'PATH': os.environ.get('PATH') or '/usr/bin:/bin', 'HOME': os.path.expanduser('~'), 'LANG': 'C.UTF-8',
            'GIT_PAGER': 'cat', 'GIT_TERMINAL_PROMPT': '0'}


def git(cwd, *args, timeout=GIT_TIMEOUT, data=None, text=True) -> subprocess.CompletedProcess:
    """Run one git command in `cwd` with a minimal environment; never raises on a non-zero exit."""
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=text, timeout=timeout,
                          env=_env(), input=data)


def _identity(folder) -> tuple:
    """Commit identity flags: none when the repository configures an email, else autogen's own."""
    return () if git(folder, 'config', 'user.email').stdout.strip() else IDENTITY


def project_top(cwd) -> str:
    """The top folder of the git repository that holds `cwd` ('' when there is none)."""
    out = git(cwd, 'rev-parse', '--show-toplevel')
    return out.stdout.strip() if out.returncode == 0 else ''


def _sub(worktree, top, cwd) -> str:
    """The folder inside `worktree` that corresponds to `cwd` inside the project `top`."""
    sub = os.path.normpath(os.path.join(worktree, os.path.relpath(os.path.realpath(cwd), top)))
    return sub if os.path.isdir(sub) else worktree


def find_checkout(cwd, name) -> dict | None:
    """An existing checkout made by make_checkout(cwd, name) (the newest when several), or None."""
    top = project_top(cwd)
    if not top:
        return None
    pattern = os.path.join(os.path.dirname(top), os.path.basename(top) + FOLDER_SUFFIX, glob.escape(name) + '-*')
    for worktree in sorted(glob.glob(pattern), reverse=True):
        leaf = os.path.basename(worktree)
        if not STAMP_RX.fullmatch(leaf[len(name) + 1:]) or not os.path.isdir(worktree):
            continue
        branch = git(worktree, 'symbolic-ref', '--short', '-q', 'HEAD').stdout.strip()
        head = git(worktree, 'rev-parse', '--verify', '-q', 'HEAD').stdout.strip()
        if branch != BRANCH_PREFIX + leaf or not head:
            continue
        return {'worktree': worktree, 'cwd': _sub(worktree, top, cwd), 'branch': branch, 'base_sha': head,
                'base_branch': git(top, 'symbolic-ref', '--short', '-q', 'HEAD').stdout.strip(),
                'main_root': top, 'carried': None, 'adopted': True}
    return None


def carry_over(top, worktree) -> dict:
    """Copy the project's uncommitted work into a fresh worktree: every change to tracked files as one
    binary patch (deletions included), then the untracked files git does not ignore."""
    patch = subprocess.run(['git', 'diff', '--binary', 'HEAD'], cwd=top, capture_output=True, timeout=GIT_TIMEOUT,
                           env=_env())
    if patch.returncode != 0:
        raise CheckoutError('Carrying the uncommitted work over: git diff failed.')
    if patch.stdout.strip():
        applied = subprocess.run(['git', 'apply', '--binary', '--whitespace=nowarn', '-'], cwd=worktree,
                                 input=patch.stdout, capture_output=True, timeout=GIT_TIMEOUT, env=_env())
        if applied.returncode != 0:
            raise CheckoutError('Carrying the uncommitted work over: '
                                + applied.stderr.decode('utf-8', 'replace').strip()[:200])
    listed = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=top,
                            capture_output=True, timeout=GIT_TIMEOUT, env=_env())
    files, skipped = 0, []
    for rel in listed.stdout.decode('utf-8', 'surrogateescape').split('\0'):
        if not rel or JUNK.search(rel):
            continue
        source, target = os.path.join(top, rel), os.path.join(worktree, rel)
        try:
            if os.path.islink(source):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.symlink(os.readlink(source), target)
            elif os.path.isfile(source):
                if os.path.getsize(source) > CARRY_MAX_BYTES:
                    skipped.append(rel)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)
            else:
                continue
        except OSError:
            skipped.append(rel)
            continue
        files += 1
    return {'files': files, 'skipped': skipped[:50]}


def _drop(top, worktree, branch) -> None:
    """Undo a half-made checkout (make_checkout verified neither existed before it started)."""
    for args in (('worktree', 'remove', '--force', '--force', worktree), ('worktree', 'prune'), ('branch', '-D', branch)):
        try:
            git(top, *args)
        except (OSError, subprocess.SubprocessError):
            pass
    shutil.rmtree(worktree, ignore_errors=True)


def make_checkout(cwd, name, *, carry=True, now=None) -> dict:
    """The attempt's own checkout of the repository holding `cwd` (adopted when it already exists)."""
    if not isinstance(name, str) or not NAME_RX.fullmatch(name):
        raise CheckoutError(f'{name!r} is not a checkout name (letters, digits, dot, underscore, hyphen).')
    found = find_checkout(cwd, name)
    if found is not None:
        return found
    top = project_top(cwd)
    if not top:
        raise CheckoutError('An own checkout needs a git repository: pick a folder inside one.')
    head = git(top, 'rev-parse', '--verify', '-q', 'HEAD').stdout.strip()
    if not head:
        raise CheckoutError('An own checkout needs at least one commit in the repository.')
    base_branch = git(top, 'symbolic-ref', '--short', '-q', 'HEAD').stdout.strip()
    stamp = (now or datetime.datetime.now()).strftime(STAMP_FORMAT)
    leaf = f'{name}-{stamp}'
    branch = BRANCH_PREFIX + leaf
    worktree = os.path.join(os.path.dirname(top), os.path.basename(top) + FOLDER_SUFFIX, leaf)
    os.makedirs(os.path.dirname(worktree), exist_ok=True)
    if os.path.lexists(worktree) or git(top, 'rev-parse', '--verify', '-q', f'refs/heads/{branch}').stdout.strip():
        raise CheckoutError('A checkout with this name was made this second: try again.')
    try:
        made = git(top, 'worktree', 'add', '-q', '-b', branch, worktree, 'HEAD')
        if made.returncode != 0:
            raise CheckoutError(f'git worktree add: {made.stderr.strip()[:200]}')
        base, carried = head, None
        if carry and git(top, 'status', '--porcelain').stdout.strip():
            carried = carry_over(top, worktree)
            git(worktree, 'add', '-A')
            committed = git(worktree, *_identity(worktree), 'commit', '-q', '--no-verify', '-m',
                            'autogen: baseline (uncommitted work carried over from the project)')
            if committed.returncode == 0:
                base = git(worktree, 'rev-parse', 'HEAD').stdout.strip() or head
                carried['head'] = head
            else:
                carried = None
    except subprocess.TimeoutExpired:
        _drop(top, worktree, branch)
        raise CheckoutError('Making the checkout took too long (the machine is busy); nothing was kept.') from None
    except BaseException:
        _drop(top, worktree, branch)
        raise
    return {'worktree': worktree, 'cwd': _sub(worktree, top, cwd), 'branch': branch, 'base_sha': base,
            'base_branch': base_branch, 'main_root': top, 'carried': carried, 'adopted': False}


def commit_all(checkout: dict, message: str) -> str:
    """Stage and commit everything in the checkout; 'Nothing to commit.' when it is clean."""
    worktree = checkout.get('worktree')
    if not worktree or not os.path.isdir(worktree):
        raise CheckoutError('The checkout folder is gone.')
    staged = git(worktree, 'add', '-A')
    if staged.returncode != 0:
        raise CheckoutError('git add: ' + staged.stderr.strip()[:200])
    if not git(worktree, 'status', '--porcelain').stdout.strip():
        return 'Nothing to commit.'
    committed = git(worktree, *_identity(worktree), 'commit', '-q', '--no-verify', '-m',
                    (message or 'autogen: work')[:100])
    if committed.returncode != 0:
        raise CheckoutError('git commit: ' + (committed.stderr or committed.stdout).strip()[:200])
    return 'Committed.'


def _blob(repo, rev, rel) -> bytes | None:
    out = subprocess.run(['git', 'cat-file', 'blob', f'{rev}:{rel}'], cwd=repo, capture_output=True, timeout=60, env=_env())
    return out.stdout if out.returncode == 0 else None


def _tree_mode(repo, rev, rel) -> str:
    out = subprocess.run(['git', 'ls-tree', '-z', rev, '--', rel], cwd=repo, capture_output=True, timeout=60, env=_env())
    head = out.stdout.split(b'\t', 1)[0].decode('ascii', 'replace') if out.returncode == 0 else ''
    return head.split(' ')[0] if head else ''


def _merge3(ours: bytes, base: bytes, theirs: bytes) -> tuple[bytes, int]:
    """git merge-file on three versions: (merged bytes, number of overlapping changes)."""
    with tempfile.TemporaryDirectory(prefix='autogen-apply-') as folder:
        paths = []
        for label, data in (('ours', ours), ('base', base), ('theirs', theirs)):
            path = os.path.join(folder, label)
            with open(path, 'wb') as handle:
                handle.write(data)
            paths.append(path)
        out = subprocess.run(['git', 'merge-file', '-p', '-L', 'project', '-L', 'base', '-L', 'attempt', *paths],
                             capture_output=True, timeout=60, env=_env())
        if out.returncode < 0:
            raise CheckoutError('git merge-file failed')
        return out.stdout, out.returncode


def apply_to_project(checkout: dict) -> dict:
    """Apply the checkout's committed changes since its baseline to the project's working tree.
    Returns {'message', 'files', 'untracked'}; raises CheckoutError on any clash (nothing applied)."""
    branch, main, worktree = checkout.get('branch'), checkout.get('main_root'), checkout.get('worktree')
    if not branch or not BRANCH_RX.match(branch):
        raise CheckoutError('Only an autogen branch (autogen/...) can be applied here.')
    if not main or not os.path.isdir(main):
        raise CheckoutError('The project repository of this checkout is gone.')
    left = []
    if worktree and os.path.isdir(worktree):
        if git(worktree, 'status', '--porcelain', '--untracked-files=no').stdout.strip():
            raise CheckoutError('The checkout has uncommitted changes: commit them first.')
        left = [line for line in git(worktree, 'ls-files', '--others', '--exclude-standard').stdout.splitlines() if line]
    tip = git(main, 'rev-parse', '--verify', '-q', f'refs/heads/{branch}').stdout.strip()
    since = checkout.get('base_sha')
    if not tip or not since:
        raise CheckoutError('Where this checkout\'s work starts is unknown.')
    if tip == since:
        return {'message': 'Nothing new to apply.', 'files': [], 'untracked': left}
    listed = subprocess.run(['git', 'diff', '--name-status', '--no-renames', '-z', since, tip], cwd=main,
                            capture_output=True, timeout=120, env=_env())
    if listed.returncode != 0:
        raise CheckoutError('git diff: ' + listed.stderr.decode('utf-8', 'replace').strip()[:200])
    parts = listed.stdout.decode('utf-8', 'surrogateescape').split('\0')
    root = os.path.realpath(main)
    plan, clashes, unchanged = [], [], 0
    for i in range(0, len(parts) - 1, 2):
        rel = parts[i + 1]
        dest = os.path.realpath(os.path.join(root, rel))
        if not rel or os.path.isabs(rel) or not dest.startswith(root + os.sep):
            clashes.append(f'{rel} (outside the project)')
            continue
        base, theirs = _blob(main, since, rel), _blob(main, tip, rel)
        ours = None
        if os.path.islink(dest):
            ours = os.readlink(dest).encode('utf-8', 'surrogateescape')
        elif os.path.isfile(dest):
            with open(dest, 'rb') as handle:
                ours = handle.read()
        mode = _tree_mode(main, tip, rel) if theirs is not None else ''
        if theirs is None:                                      # the attempt deleted it
            if ours is None:
                unchanged += 1
            elif ours == base:
                plan.append(('delete', rel, dest, None, ''))
            else:
                clashes.append(f'{rel} (the attempt deleted it; the project changed it)')
        elif base is None:                                      # the attempt added it
            if ours is None:
                plan.append(('write', rel, dest, theirs, mode))
            elif ours == theirs:
                unchanged += 1
            else:
                clashes.append(f'{rel} (the attempt added it; the project\'s differs)')
        elif ours == theirs:
            unchanged += 1
        elif ours == base:
            plan.append(('write', rel, dest, theirs, mode))
        elif ours is None:
            clashes.append(f'{rel} (the project deleted it; the attempt changed it)')
        elif b'\0' in ours or b'\0' in base or b'\0' in theirs or mode == '120000':
            clashes.append(f'{rel} (binary; both sides changed it)')
        else:
            merged, overlaps = _merge3(ours, base, theirs)
            if overlaps:
                clashes.append(f'{rel} ({overlaps} overlapping change{"s" if overlaps > 1 else ""})')
            elif merged == ours:                                # already applied: nothing to write
                unchanged += 1
            else:
                plan.append(('write', rel, dest, merged, mode))
    if clashes:
        more = f' and {len(clashes) - 8} more' if len(clashes) > 8 else ''
        raise CheckoutError(f'Nothing was applied: {len(clashes)} file(s) clash with your checkout: '
                            + '; '.join(clashes[:8]) + more)
    for op, rel, dest, data, mode in plan:
        if op == 'delete':
            os.remove(dest)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if mode == '120000':
            if os.path.lexists(dest):
                os.remove(dest)
            os.symlink(data.decode('utf-8', 'surrogateescape'), dest)
            continue
        keep = os.stat(dest).st_mode & 0o777 if os.path.isfile(dest) and not os.path.islink(dest) else 0o644
        fd, temporary = tempfile.mkstemp(prefix='.autogen-apply-', dir=os.path.dirname(dest))
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.chmod(temporary, (keep | 0o111) if mode == '100755' else (keep & ~0o111 if mode == '100644' else keep))
        os.replace(temporary, dest)
    files = [entry[1] for entry in plan]
    message = (f'Applied {len(files)} file(s) from {branch} into {main} (not committed)'
               + (f'; {unchanged} already matched' if unchanged else '') + '.')
    if left:
        message += (f' Not applied, never committed in its checkout: {", ".join(left[:5])}'
                    + (f' and {len(left) - 5} more' if len(left) > 5 else '') + '.')
    return {'message': message, 'files': files, 'untracked': left}
